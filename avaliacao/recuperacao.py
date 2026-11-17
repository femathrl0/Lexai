"""Avaliação da recuperação conjunta com os gabaritos existentes na base.

Legislação: data/evaluation/legislacao/eval_dataset_{dev,test}_aprovado.json — perguntas respondíveis com
norma e artigo esperados (casados com `caminho_relativo` e `artigo_ref` dos metadados do corpus).
Jurisprudência: data/evaluation/jurisprudencia/perguntas_suporte.jsonl — perguntas de ajuste com intervalos
de suporte anotados (registro_id, campo, início e fim no documento-base protegido). A reserva do teste final
do notebook 04 de jurisprudência não é usada aqui.

Métricas por pergunta, no ranking de unidades (artigos/decisões) após a combinação:
  - posição da primeira unidade relevante → Hit@k e MRR@10;
  - jurisprudência: cobertura de suporte@k = fração dos caracteres da melhor alternativa de suporte coberta
    pelos chunks recuperados nas k primeiras unidades.
"""
from __future__ import annotations

from pathlib import Path
import json
import re
import time

import pandas as pd

KS = (1, 3, 5, 10)


def _norm_artigo(valor):
    return re.sub(r'[\sº°ªo]+$', '', re.sub(r'\s+', ' ', str(valor or '').strip()).replace('°', 'º')).lower()


def gabarito_legislacao(root):
    perguntas = []
    for nome in ('dev', 'test'):
        for q in json.loads((Path(root) / f'avaliacao/dados/legislacao/eval_dataset_{nome}_aprovado.json').read_text(encoding='utf-8')):
            if str(q.get('elegivel_metricas')) == 'True' and q.get('rotulo_resposta') == 'respondível' and q.get('artigo_esperado'):
                perguntas.append(dict(fonte='legislacao', query_id=q['query_id'], pergunta=q['pergunta'],
                                      norma=q['norma_esperada'], artigo=q['artigo_esperado']))
    return perguntas


def gabarito_jurisprudencia(root):
    caminho = Path(root) / 'avaliacao/dados/jurisprudencia/perguntas_suporte.jsonl'
    perguntas = []
    for linha in caminho.read_text(encoding='utf-8').splitlines():
        if not linha.strip():
            continue
        q = json.loads(linha)
        alternativas = q.get('alternativas_suporte') or []
        if alternativas:
            perguntas.append(dict(fonte='jurisprudencia', query_id=q['query_id'], pergunta=q['pergunta'],
                                  alternativas=alternativas,
                                  registros={r['registro_id'] for g in alternativas for r in g}))
    return perguntas


def relevante(pergunta, unidade, metadata):
    if pergunta['fonte'] == 'legislacao':
        return (unidade[0] == 'legislacao' and metadata.get('caminho_relativo') == pergunta['norma']
                and _norm_artigo(metadata.get('artigo_ref')) == _norm_artigo(pergunta['artigo']))
    return unidade[0] == 'jurisprudencia' and unidade[1] in pergunta['registros']


def cobertura_suporte(pergunta, chunks):
    """Melhor alternativa: fração dos caracteres anotados cobertos pelos chunks recuperados."""
    melhor = 0.0
    for grupo in pergunta['alternativas']:
        total = coberto = 0
        for ref in grupo:
            total += ref['fim'] - ref['inicio']
            intervalos = sorted((int(m['inicio']), int(m['fim'])) for c in chunks
                                for m in [c['metadata']] if c['unidade'] == ref['registro_id']
                                and m.get('campo_texto') == ref['campo_texto'])
            fim_coberto = ref['inicio']
            for a, b in intervalos:
                a, b = max(a, fim_coberto), min(b, ref['fim'])
                if b > a:
                    coberto += b - a
                    fim_coberto = b
        if total:
            melhor = max(melhor, coberto / total)
    return melhor


def avaliar(recuperador, perguntas, config, rotulo):
    """Executa as perguntas e devolve um DataFrame com uma linha por pergunta."""
    linhas = []
    for q in perguntas:
        inicio = time.monotonic()
        entregues, diag = recuperador.buscar(q['pergunta'], config)
        # Metadados de todas as unidades do ranking (não só as entregues) para localizar a posição relevante.
        meta_unidade = {}
        for c in diag['candidatos_detalhe']:
            meta_unidade.setdefault((c['fonte'], c['unidade']), c['metadata'])
        # Com cotas por fonte, a posição é contada dentro da lista da fonte da pergunta (são entregues separadas).
        ranking = diag['ranking_por_fonte'][q['fonte']] if diag.get('com_cotas') else diag['ranking_unidades']
        posicao = next((i for i, u in enumerate(ranking, 1) if relevante(q, u, meta_unidade.get(u, {}))), None)
        linha = dict(configuracao=rotulo, fonte=q['fonte'], query_id=q['query_id'], posicao=posicao,
                     segundos=time.monotonic() - inicio, unidades=diag['unidades'])
        for k in KS:
            linha[f'hit@{k}'] = int(posicao is not None and posicao <= k)
        linha['mrr@10'] = (1 / posicao) if posicao and posicao <= 10 else 0.0
        if q['fonte'] == 'jurisprudencia':
            todos = diag.get('candidatos_detalhe') or []
            for k in (3, 5):
                topo = set(ranking[:k])
                chunks = [c for c in todos if (c['fonte'], c['unidade']) in topo]
                linha[f'cobertura@{k}'] = cobertura_suporte(q, chunks)
        linhas.append(linha)
    return pd.DataFrame(linhas)


def resumo(df):
    colunas = [c for c in df.columns if c.startswith(('hit@', 'mrr', 'cobertura'))]
    tabela = df.groupby(['configuracao', 'fonte'])[colunas + ['segundos']].mean().round(3)
    tabela['perguntas'] = df.groupby(['configuracao', 'fonte']).size()
    return tabela.reset_index()
