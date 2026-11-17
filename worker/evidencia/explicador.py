"""Geração das respostas do fluxo integrado: pedidos para a LLM, respostas fixas e validação do retorno.

Fluxo por pergunta:
  1. guardrail de entrada (`guardrails.verificar_entrada`) → ação e pergunta sanitizada;
  2. ações `responder` e `orientar_sem_aconselhar`: recuperação conjunta com a configuração padrão e montagem do
     prompt jurídico (`prompt_juridico`) com as fontes entregues;
  3. demais ações (institucional, consulta individual, fora do escopo, outra jurisdição): resposta fixa, sem LLM;
  4. a LLM roda fora daqui (Kaggle, GPU T4, Ollama) sobre os pedidos exportados;
  5. no retorno, `validar_resposta` confere integridade e formato, e `guardrails.verificar_saida` revisa o conteúdo.
"""
from __future__ import annotations

import hashlib
import json
import re

from . import guardas as g
from .prompts import SYSTEM_PROMPT_LEGAL, build_rag_prompt

MODELO_GERACAO = 'qwen3:8b-q8_0'
# num_ctx 16384: o maior prompt (6 fontes, artigos longos) passa de 10 mil tokens; com 8192 o Ollama cortaria o início.
OPCOES_GERACAO = dict(temperature=0, seed=42, num_predict=1200, num_ctx=16384)
ACOES_COM_BUSCA = ('responder', 'orientar_sem_aconselhar')

RESPOSTAS_FIXAS = {
    'institucional': ('Esta pergunta é sobre o funcionamento da plataforma, e não sobre Direito do Trabalho. '
                      'As informações sobre uso, privacidade e funcionalidades estão na página de ajuda da LexIA. '
                      'Se quiser, faça uma pergunta sobre seus direitos trabalhistas que eu explico com base na legislação '
                      'e na jurisprudência.'),
    'consulta_individual': ('Não tenho acesso a processos, contas ou registros pessoais, então não consigo informar a '
                            'situação do seu caso. Consulte o processo pelo número no site do tribunal (sistema PJe), ou '
                            'fale com o advogado que acompanha a ação. Para o FGTS, o extrato fica no aplicativo FGTS da '
                            'Caixa. Não envie aqui seu CPF, número do processo ou documentos.'),
    'fora_escopo': ('Só consigo responder perguntas sobre Direito do Trabalho brasileiro. Para outros assuntos, procure '
                    'um profissional da área ou a Defensoria Pública.'),
    'outra_jurisdicao': ('Só consigo responder sobre o Direito do Trabalho brasileiro. Para as regras de outro país, '
                         'consulte a legislação local ou um profissional habilitado nesse país.'),
}
NOTA_CASO_CONCRETO = ('\nA pergunta descreve uma situação concreta. Explique a regra geral aplicável com base nas fontes, '
                      'indique o que costuma ser verificado em casos assim e recomende procurar um advogado, a Defensoria '
                      'Pública ou o sindicato. Não diga o que a pessoa deve fazer nem preveja o resultado.\n')


def _processo_formatado(numero):
    d = re.sub(r'\D', '', str(numero or ''))
    return f'{d[:7]}-{d[7:9]}.{d[9:13]}.{d[13]}.{d[14:16]}.{d[16:20]}' if len(d) == 20 else (numero or None)


def _valor(meta, chave):
    v = meta.get(chave)
    return None if v in (None, '', 'None', 'nan') else v


def fonte_para_prompt(unidade):
    """Converte uma unidade entregue pelo Recuperador no formato de `build_rag_prompt` e dos guardrails."""
    meta = unidade.get('metadata') or {}
    if unidade['fonte'] == 'legislacao':
        return dict(fonte='legislacao', unidade=unidade['unidade'], conteudo=unidade['texto'],
                    caminho_relativo=_valor(meta, 'caminho_relativo'), artigo_ref=_valor(meta, 'artigo_ref'),
                    contexto=_valor(meta, 'contexto'), status_declarado=_valor(meta, 'status_declarado'))
    return dict(fonte='jurisprudencia', unidade=unidade['unidade'], conteudo=unidade['texto'],
                tribunal=_valor(meta, 'tribunal'), processo=_processo_formatado(_valor(meta, 'processo_cnj')),
                orgao_julgador=_valor(meta, 'orgao_julgador'),
                data_julgamento=_valor(meta, 'data_julgamento') or _valor(meta, 'data_publicacao') or _valor(meta, 'data_assinatura'),
                artigo_ref=None)


def _hash(*partes):
    return hashlib.sha256(json.dumps(partes, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


def montar_pedido(pergunta_id, pergunta, recuperador, config):
    """Devolve o pedido de uma pergunta: com prompt para a LLM ou com resposta fixa."""
    entrada = g.verificar_entrada(pergunta)
    base = dict(pergunta_id=pergunta_id, acao=entrada.acao, sinais=entrada.sinais, motivo=entrada.motivo,
                pergunta_sanitizada=entrada.pergunta_sanitizada)
    if entrada.acao not in ACOES_COM_BUSCA:
        return dict(base, precisa_llm=False, fontes=[], resposta_fixa=RESPOSTAS_FIXAS[entrada.acao])
    entregues, diag = recuperador.buscar(entrada.pergunta_sanitizada, config)
    fontes = [fonte_para_prompt(u) for u in entregues]
    sistema, usuario = build_rag_prompt(entrada.pergunta_sanitizada, fontes)
    if entrada.acao == 'orientar_sem_aconselhar':
        usuario += NOTA_CASO_CONCRETO
    mensagens = [dict(role='system', content=sistema), dict(role='user', content=usuario)]
    return dict(base, precisa_llm=True, fontes=fontes, mensagens=mensagens, segundos_recuperacao=round(diag['segundos'], 1),
                pedido_sha256=_hash(MODELO_GERACAO, OPCOES_GERACAO, mensagens))


def validar_resposta(pedido, resposta):
    """Problemas de integridade/formato de uma resposta da LLM (lista vazia = válida)."""
    problemas = []
    if resposta.get('pedido_sha256') != pedido.get('pedido_sha256'):
        problemas.append('hash do pedido diferente')
    texto = (resposta.get('resposta') or '').strip()
    if len(texto) < 80:
        problemas.append('resposta vazia ou curta')
    if resposta.get('done_reason') == 'length':
        problemas.append('resposta cortada no limite de tokens')
    if re.search(r'</?think>', texto):
        problemas.append('raciocínio interno na resposta')
    return problemas


def revisar(pedido, texto):
    """Guardrail de saída com as fontes do pedido."""
    fontes = [dict(texto=f['conteudo'], artigo_ref=f.get('artigo_ref'), processo=f.get('processo')) for f in pedido['fontes']]
    entrada = g.ResultadoEntrada(pedido['acao'], pedido['pergunta_sanitizada'], pedido['sinais'], pedido['motivo'])
    return g.verificar_saida(texto, fontes, entrada)
