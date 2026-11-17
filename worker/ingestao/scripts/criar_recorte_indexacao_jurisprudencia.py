"""Cria o recorte de indexação do notebook 05: amostra estratificada de ~20 mil documentos.

Motivo (decisão de 16/11/2026): indexar os 169.821 candidatos gera 2,57 milhões de chunks (~19 h de GPU),
o que torna o projeto difícil de reproduzir. Os notebooks 01–04 continuam com a base reduzida completa
(179.812 registros); somente o chunking definitivo e os embeddings usam este recorte.

Seleção:
  - parte dos candidatos consolidados do notebook 03 (índice automático ativo);
  - inclui obrigatoriamente os documentos usados nos experimentos do notebook 04 e na avaliação;
  - completa até TOTAL por amostragem estratificada proporcional (tribunal x ano x órgão julgador),
    com seed fixa e alocação pelos maiores restos.

Saída: reports/jurisprudencia/base_reduzida/recorte_indexacao.json, lido por chunking_definitivo.prepare.
Uso: python scripts/criar_recorte_indexacao_jurisprudencia.py [--total 20000]
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import json
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from worker.ingestao.jurisprudencia import audit, automatic_review, light_nlp  # noqa: E402

SEED = 20261116
SAIDA = ROOT / 'dados/relatorios/jurisprudencia/base_reduzida/recorte_indexacao.json'


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser()
    parser.add_argument('--total', type=int, default=20_000)
    total = parser.parse_args().total
    _, auto = automatic_review.load(ROOT)
    pln_dir, pln = light_nlp.load(ROOT)
    indice = pd.read_parquet(ROOT / auto['indice'], columns=['registro_id', 'tribunal', 'candidato_consolidado'])
    cand = indice[indice.candidato_consolidado].copy()
    meta = pd.concat([pd.read_parquet(ROOT / f['arquivo'], columns=['registro_id', 'data_julgamento', 'data_publicacao', 'orgao_julgador'])
                      for f in pln['arquivos']])
    cand = cand.merge(meta, on='registro_id', how='left')
    data = pd.to_datetime(cand.data_julgamento.fillna(cand.data_publicacao), errors='coerce')
    cand['estrato'] = cand.tribunal + '|' + data.dt.year.fillna(0).astype(int).astype(str) + '|' + cand.orgao_julgador.fillna('sem_orgao')
    # Obrigatórios: IDs da base completa convertidos para os IDs da base reduzida.
    mapa = pd.read_parquet(ROOT / 'dados/relatorios/jurisprudencia/base_reduzida/mapa_registro_id.parquet',
                           columns=['registro_id_base_completa', 'registro_id_novo'])
    antigos = set(json.loads((ROOT / 'dados/relatorios/jurisprudencia/base_reduzida/ids_obrigatorios.json').read_text(encoding='utf-8'))['registro_ids'])
    obrig = set(mapa[mapa.registro_id_base_completa.isin(antigos)].registro_id_novo)
    if not obrig <= set(cand.registro_id):
        raise RuntimeError('Documento obrigatório fora dos candidatos consolidados.')
    forcados = cand[cand.registro_id.isin(obrig)]
    livres = cand[~cand.registro_id.isin(obrig)].sort_values('registro_id')
    vagas = total - len(forcados)
    tam = livres.groupby('estrato').size()
    cota = tam / tam.sum() * vagas
    base = np.floor(cota).astype(int)
    base[(cota - base).sort_values(ascending=False, kind='mergesort').index[:vagas - base.sum()]] += 1
    rng = np.random.default_rng(SEED)
    escolhidos = [forcados]
    for estrato, grupo in livres.groupby('estrato', sort=True):
        n = int(base[estrato])
        if n:
            escolhidos.append(grupo.iloc[np.sort(rng.choice(len(grupo), size=n, replace=False))])
    sel = pd.concat(escolhidos)
    if len(sel) != total or not sel.registro_id.is_unique:
        raise RuntimeError('Recorte com tamanho ou IDs inconsistentes.')
    valor = dict(
        protocolo='jurisprudencia-recorte-indexacao-v1', criado_em_utc=datetime.now(timezone.utc).isoformat(),
        motivo='Reduzir chunks e embeddings para tornar o projeto reprodutível; notebooks 01–04 mantêm a base completa.',
        criterios=dict(origem='candidato_consolidado do índice automático ativo (notebook 03)',
                       obrigatorios=f'{len(forcados)} documentos dos experimentos do notebook 04 e da avaliação',
                       amostragem='estratificada proporcional por tribunal x ano x órgão julgador, maiores restos', seed=SEED),
        indice_sha256=auto['indice_sha256'], base_pln_csv_sha256=pln['csv_sha256'],
        candidatos=len(cand), documentos=len(sel), obrigatorios=len(forcados),
        por_tribunal=sel.tribunal.value_counts().to_dict(), registro_ids=sorted(sel.registro_id))
    audit.write_json(SAIDA, valor)
    print('Recorte:', len(sel), 'documentos de', len(cand), '| obrigatórios:', len(forcados), '| por tribunal:', valor['por_tribunal'])


if __name__ == '__main__':
    main()
