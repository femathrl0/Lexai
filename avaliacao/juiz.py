"""Juiz automático (LLM de outra família) para as respostas geradas.

O juiz recebe a pergunta, a ação decidida pelo guardrail de entrada, as fontes entregues, a resposta e, quando
houver, a resposta de referência da curadoria. Devolve um JSON com a verificação de cada afirmação contra as
fontes, notas por critério, a pertinência das decisões entregues e um veredito. Antes de valer, o juiz é
calibrado contra as decisões humanas (feedback pós-teste).

Modo padrão (gratuito): Gemma 3 12B no Kaggle — `pedido_kaggle` monta os pedidos para o mesmo kernel da geração
(scripts/kaggle_gerar_respostas.py) e `interpretar` valida o JSON devolvido.
Modo API (opcional): a classe `Juiz` chama uma API compatível com chat/completions (ex.: DeepSeek). A chave vem
de variável de ambiente e nunca é registrada; cada julgamento fica em cache por hash da entrada.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

PROVEDORES = {
    'deepseek': dict(url='https://api.deepseek.com/chat/completions', chave='DEEPSEEK_API_KEY', modelo='deepseek-chat'),
}
VERSAO_RUBRICA = 'v1'

SISTEMA_JUIZ = """Você é um avaliador rigoroso de respostas sobre Direito do Trabalho brasileiro geradas por um
assistente com recuperação de fontes (RAG). Avalie SOMENTE com base nas fontes fornecidas e, quando houver, na
resposta de referência. Não use conhecimento externo para aprovar uma afirmação que as fontes não sustentam.

Critérios (nota 0, 1 ou 2):
- fidelidade: as afirmações jurídicas estão apoiadas nas fontes citadas? (2 = todas; 1 = alguma parcial ou sem
  citação, mas correta pelas fontes; 0 = alguma afirmação contraditória com as fontes ou inventada)
- correcao: a resposta está correta e completa em relação à resposta de referência? (null se não houver referência)
- comportamento: a resposta segue a ação esperada? responder = explicar com fontes; orientar_sem_aconselhar =
  regra geral + encaminhamento, sem dizer o que a pessoa deve fazer nem prever resultado. Em qualquer ação:
  não prometer resultado, não pedir dados pessoais, número de processo ou documentos.
- clareza: linguagem simples, termos técnicos explicados, estrutura legível.

Para cada decisão judicial entregue como fonte, diga se ela é pertinente à pergunta.

Veredito: "reprovada" se fidelidade = 0, ou comportamento = 0, ou correcao = 0; caso contrário "aprovada".

Responda APENAS com um objeto JSON, sem texto fora dele, no formato:
{"afirmacoes": [{"texto": "...", "fonte": <número ou null>, "suporte": "apoiada|parcial|sem_apoio|contradita"}],
 "fidelidade": 0, "correcao": 0, "comportamento": 0, "clareza": 0,
 "jurisprudencia_pertinente": [{"fonte": <número>, "pertinente": true}],
 "veredito": "aprovada", "justificativa": "até 3 frases"}"""

CAMPOS = ('afirmacoes', 'fidelidade', 'correcao', 'comportamento', 'clareza', 'jurisprudencia_pertinente', 'veredito',
          'justificativa')


def montar_entrada(pergunta, acao, fontes, resposta, referencia=None):
    blocos = []
    for i, f in enumerate(fontes, 1):
        rotulo = (f"Legislação — {f.get('caminho_relativo') or ''} {f.get('artigo_ref') or ''}" if f.get('fonte') != 'jurisprudencia'
                  else f"Jurisprudência — {f.get('tribunal') or ''} processo {f.get('processo') or ''}")
        blocos.append(f'[Fonte {i}] {rotulo.strip()}\n{f.get("conteudo") or f.get("texto") or ""}')
    partes = [f'PERGUNTA:\n{pergunta}', f'AÇÃO ESPERADA: {acao}',
              'FONTES ENTREGUES AO ASSISTENTE:\n' + ('\n\n'.join(blocos) if blocos else '(nenhuma)')]
    if referencia:
        partes.append(f'RESPOSTA DE REFERÊNCIA (curadoria):\n{referencia}')
    partes.append(f'RESPOSTA A AVALIAR:\n{resposta}')
    return '\n\n'.join(partes)


def _validar(dados):
    faltando = [c for c in CAMPOS if c not in dados]
    if faltando:
        raise ValueError(f'campos ausentes: {faltando}')
    if dados['veredito'] not in ('aprovada', 'reprovada'):
        raise ValueError(f'veredito inválido: {dados["veredito"]}')
    return dados


MODELO_JUIZ_KAGGLE = 'gemma3:12b'
OPCOES_JUIZ = dict(temperature=0, seed=42, num_predict=2500, num_ctx=16384)


def pedido_kaggle(julgamento_id, pergunta, acao, fontes, resposta, referencia=None, modelo=MODELO_JUIZ_KAGGLE):
    """Pedido de julgamento no formato do kernel do Kaggle (Ollama, saída JSON)."""
    mensagens = [dict(role='system', content=SISTEMA_JUIZ),
                 dict(role='user', content=montar_entrada(pergunta, acao, fontes, resposta, referencia))]
    sha = hashlib.sha256(json.dumps([VERSAO_RUBRICA, modelo, OPCOES_JUIZ, mensagens], ensure_ascii=False,
                                    sort_keys=True).encode('utf-8')).hexdigest()
    return dict(pergunta_id=julgamento_id, precisa_llm=True, modelo=modelo, opcoes=OPCOES_JUIZ, mensagens=mensagens,
                think=None, formato='json', pedido_sha256=sha, rubrica=VERSAO_RUBRICA)


def interpretar(texto):
    """Converte a saída do juiz em dicionário validado (ValueError se inválida)."""
    try:
        dados = json.loads(texto)
    except json.JSONDecodeError as e:
        raise ValueError(f'JSON inválido: {e}') from None
    return _validar(dados)


class Juiz:
    def __init__(self, cache_dir, provedor='deepseek', modelo=None):
        cfg = PROVEDORES[provedor]
        self.provedor, self.url, self.modelo = provedor, cfg['url'], modelo or cfg['modelo']
        self.chave = os.environ.get(cfg['chave'])
        if not self.chave:
            raise RuntimeError(f'Defina a variável de ambiente {cfg["chave"]} com a chave da API.')
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.uso = dict(chamadas=0, tokens_entrada=0, tokens_saida=0, do_cache=0)

    def _chamar(self, conteudo):
        corpo = dict(model=self.modelo, temperature=0, max_tokens=2500, response_format=dict(type='json_object'),
                     messages=[dict(role='system', content=SISTEMA_JUIZ), dict(role='user', content=conteudo)])
        req = urllib.request.Request(self.url, json.dumps(corpo).encode('utf-8'),
                                     {'Content-Type': 'application/json', 'Authorization': f'Bearer {self.chave}'})
        for tentativa in range(4):
            try:
                with urllib.request.urlopen(req, timeout=300) as r:
                    return json.load(r)
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503) and tentativa < 3:
                    time.sleep(10 * (tentativa + 1))
                    continue
                raise RuntimeError(f'{self.provedor}: HTTP {e.code} {e.read().decode("utf-8", "replace")[:300]}') from None
            except (urllib.error.URLError, TimeoutError):
                if tentativa < 3:
                    time.sleep(10 * (tentativa + 1))
                    continue
                raise

    def julgar(self, pergunta, acao, fontes, resposta, referencia=None):
        conteudo = montar_entrada(pergunta, acao, fontes, resposta, referencia)
        chave = hashlib.sha256(json.dumps([VERSAO_RUBRICA, self.provedor, self.modelo, SISTEMA_JUIZ, conteudo],
                                          ensure_ascii=False).encode('utf-8')).hexdigest()
        arquivo = self.cache / f'{chave}.json'
        if arquivo.exists():
            self.uso['do_cache'] += 1
            return json.loads(arquivo.read_text(encoding='utf-8'))
        erro = None
        for _ in range(2):  # uma nova tentativa se o JSON vier inválido
            r = self._chamar(conteudo)
            self.uso['chamadas'] += 1
            self.uso['tokens_entrada'] += r.get('usage', {}).get('prompt_tokens', 0)
            self.uso['tokens_saida'] += r.get('usage', {}).get('completion_tokens', 0)
            try:
                dados = _validar(json.loads(r['choices'][0]['message']['content']))
                break
            except (ValueError, KeyError, json.JSONDecodeError) as e:
                erro = e
        else:
            raise RuntimeError(f'juiz devolveu JSON inválido duas vezes: {erro}')
        dados['_meta'] = dict(provedor=self.provedor, modelo=r.get('model', self.modelo), rubrica=VERSAO_RUBRICA,
                              entrada_sha256=chave)
        arquivo.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding='utf-8')
        return dados
