"""Cria a base reduzida de jurisprudência (opção D = A + B) nos formatos originais.

Seleção, calculada sobre a base completa já processada:
  - parte do recorte consolidado do notebook 03 (candidato_consolidado);
  - A: mantém um documento por processo (o de maior texto; registros sem processo são mantidos);
  - B: limita o TST a 100.000 documentos por amostragem estratificada (ano x órgão julgador, seed fixa),
    mantendo integralmente TRTs e STF trabalhista;
  - documentos citados nos gabaritos/curadoria de avaliação são sempre incluídos.

Saída: os mesmos nomes de arquivo originais em data/raw/jurisprudencia/base_reduzida/, cada um somente
com os registros selecionados, na ordem original e no formato original (JSONL, JSON e Parquet).
Os originais em Downloads não são alterados. Também grava o mapa registro_id antigo -> novo.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re
import sys

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from worker.ingestao.jurisprudencia import audit  # noqa: E402

SEED = 20261116
LIMITE_TST = 100_000
ORIGINAIS = Path.home() / 'Downloads'
SAIDA = ROOT / 'dados/raw/jurisprudencia/base_reduzida'
RELATORIO = ROOT / 'dados/relatorios/jurisprudencia/base_reduzida'
ESTRUTURA = ROOT / 'dados/processed/jurisprudencia/71714343f9fd896da188fc14ed120ae9b8343b744455f40aba12edfb2536242f/1cfddb551ec7c1f00d5c9bf2b6b9ab7ba990b2a6202815bb092b94443b3cbc50'
PLN = ROOT / 'dados/processed/jurisprudencia/pln_leve/349ae9df1d20a5b88cee56f116eba2d8e2a3e104e013c7a7b8cf084d132ac1ee'
INDICE = ROOT / 'dados/processed/jurisprudencia/automacao/4dfbcfe6b1cf461dbea9698d1b6f8b5843ef985702621493467483ce57b49bce/indice_automatico.parquet'


def ids_avaliacao():
    """IDs obrigatórios: gabaritos/curadoria e todos os documentos usados nos experimentos do notebook 04."""
    ids = set()
    for p in (ROOT / 'avaliacao/dados/jurisprudencia').rglob('*'):
        if p.is_file() and p.suffix in ('.json', '.jsonl'):
            ids |= set(re.findall(r'"registro_id"\s*:\s*"([0-9a-f]{64})"', p.read_text(encoding='utf-8', errors='ignore')))
    obrigatorios = RELATORIO / 'ids_obrigatorios.json'
    if obrigatorios.exists():
        ids |= set(json.loads(obrigatorios.read_text(encoding='utf-8'))['registro_ids'])
    return ids


def selecionar():
    est = pd.concat([pd.read_parquet(p, columns=['registro_id', 'arquivo_id', 'arquivo_origem', 'linha_origem', 'registro_original_sha256'])
                     for p in sorted(ESTRUTURA.glob('f??.parquet'))])
    pln = pd.concat([pd.read_parquet(p, columns=['registro_id', 'data_julgamento', 'data_publicacao', 'orgao_julgador'])
                     for p in sorted(PLN.glob('f??.parquet'))])
    idx = pd.read_parquet(INDICE, columns=['registro_id', 'tribunal', 'candidato_consolidado', 'grupo_processo', 'texto_caracteres'])
    d = est.merge(pln, on='registro_id').merge(idx, on='registro_id')
    assert len(d) == len(est) == 609_872
    aval = ids_avaliacao()
    d['avaliacao'] = d.registro_id.isin(aval)
    c = d[d.candidato_consolidado].copy()
    etapas = {'base_completa': len(d), 'recorte_consolidado': len(c)}
    # A: um por processo; prioridade para documentos da avaliação e depois maior texto.
    c['grupo'] = c.grupo_processo.fillna('sem_processo_' + c.registro_id)
    c = c.sort_values(['avaliacao', 'texto_caracteres', 'registro_id'], ascending=[False, False, True])
    a = c.drop_duplicates('grupo')
    a = pd.concat([a, c[c.avaliacao & ~c.registro_id.isin(a.registro_id)]])
    etapas['apos_A_um_por_processo'] = len(a)
    # B: TST estratificado por ano x órgão julgador, alocação proporcional (maiores restos).
    tst = a[a.tribunal == 'TST'].copy()
    outros = a[a.tribunal != 'TST']
    data = pd.to_datetime(tst.data_julgamento.fillna(tst.data_publicacao), errors='coerce')
    tst['estrato'] = data.dt.year.fillna(0).astype(int).astype(str) + '|' + tst.orgao_julgador.fillna('sem_orgao')
    forcados = tst[tst.avaliacao]
    livres = tst[~tst.avaliacao]
    vagas = LIMITE_TST - len(forcados)
    tam = livres.groupby('estrato').size()
    cota = tam / tam.sum() * vagas
    base = np.floor(cota).astype(int)
    resto = vagas - base.sum()
    base[(cota - base).sort_values(ascending=False, kind='mergesort').index[:resto]] += 1
    rng = np.random.default_rng(SEED)
    escolhidos = []
    for estrato, grupo in livres.sort_values('registro_id').groupby('estrato', sort=True):
        n = int(base[estrato])
        if n:
            escolhidos.append(grupo.iloc[np.sort(rng.choice(len(grupo), size=n, replace=False))])
    tst_sel = pd.concat([forcados, *escolhidos])
    assert len(tst_sel) == LIMITE_TST
    sel = pd.concat([outros, tst_sel])
    etapas['apos_B_tst_limitado'] = len(sel)
    # Arquivos legíveis sem nenhum candidato (ex.: JSON TST com textos curtos e origem não confirmada)
    # permanecem no inventário com o critério A aplicado, sem se tornarem candidatos ao RAG.
    sem_candidatos = sorted(set(d.arquivo_id) - set(sel.arquivo_id))
    extras = d[d.arquivo_id.isin(sem_candidatos)].copy()
    extras['grupo'] = extras.grupo_processo.fillna('sem_processo_' + extras.registro_id)
    extras = extras.sort_values(['texto_caracteres', 'registro_id'], ascending=[False, True]).drop_duplicates('grupo')
    sel = pd.concat([sel, extras])
    etapas['arquivos_sem_candidatos_mantidos_no_inventario'] = {a: int((extras.arquivo_id == a).sum()) for a in sem_candidatos}
    etapas['total_base_reduzida'] = len(sel)
    assert sel.registro_id.is_unique
    faltando = aval - set(sel.registro_id)
    if faltando:
        raise RuntimeError(f'{len(faltando)} documentos obrigatórios fora do recorte consolidado.')
    estratos = pd.DataFrame({'registros_disponiveis': tam, 'selecionados': base}).reset_index()
    return sel, etapas, estratos, len(aval)


def gravar_jsonl(origem, destino, linhas):
    mapa = {}
    novo = 0
    with origem.open(encoding='utf-8-sig') as f, destino.open('w', encoding='utf-8', newline='\n') as out:
        for numero, linha in enumerate(f, 1):
            if numero in linhas:
                novo += 1
                out.write(linha if linha.endswith('\n') else linha + '\n')
                mapa[numero] = novo
    return mapa


def gravar_json(origem, destino, linhas):
    with origem.open(encoding='utf-8-sig') as f:
        itens = json.load(f)
    mapa, saida = {}, []
    for numero, item in enumerate(itens, 1):
        if numero in linhas:
            saida.append(item)
            mapa[numero] = len(saida)
    destino.write_text(json.dumps(saida, ensure_ascii=False), encoding='utf-8')
    return mapa


def gravar_parquet(origem, destino, linhas):
    arquivo = pq.ParquetFile(origem)
    schema = arquivo.schema_arrow
    mapa, offset, novo, partes = {}, 0, 0, []
    for batch in arquivo.iter_batches(batch_size=4096, use_threads=False):
        posicoes = [i for i in range(batch.num_rows) if offset + i + 1 in linhas]
        for i in posicoes:
            novo += 1
            mapa[offset + i + 1] = novo
        if posicoes:
            partes.append(batch.take(pa.array(posicoes)))
        offset += batch.num_rows
    # Mesmo codec e tamanho de row group dos originais (ZSTD, 2.000 linhas); nível 9 evita inflar o arquivo.
    pq.write_table(pa.Table.from_batches(partes, schema=schema), destino, compression='zstd',
                   compression_level=9, row_group_size=2000)
    return mapa


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    SAIDA.mkdir(parents=True, exist_ok=True)
    RELATORIO.mkdir(parents=True, exist_ok=True)
    sel, etapas, estratos, n_aval = selecionar()
    print('Etapas da seleção:', etapas, flush=True)
    mapas, arquivos = [], []
    for (arquivo_id, nome), grupo in sel.groupby(['arquivo_id', 'arquivo_origem'], sort=True):
        origem, destino = ORIGINAIS / nome, SAIDA / nome
        linhas = set(int(x) for x in grupo.linha_origem)
        sufixo = origem.suffix.lower()
        gravar = gravar_jsonl if sufixo == '.jsonl' else gravar_json if sufixo == '.json' else gravar_parquet
        temporario = destino.with_name(destino.name + '.partial')
        mapa = gravar(origem, temporario, linhas)
        if len(mapa) != len(linhas):
            raise RuntimeError(f'{nome}: {len(mapa)} registros gravados, {len(linhas)} esperados.')
        temporario.replace(destino)
        sha = audit.hash_file(destino)
        g = grupo.assign(linha_nova=grupo.linha_origem.map(mapa))
        g['registro_id_novo'] = [audit.digest(f'{sha}|{arquivo_id}|{n}'.encode()) for n in g.linha_nova]
        mapas.append(g)
        arquivos.append(dict(arquivo_id=arquivo_id, arquivo=nome, formato=sufixo.lstrip('.'), registros=len(mapa),
                             bytes=destino.stat().st_size, sha256=sha, origem_sha256=audit.hash_file(origem)))
        print(f'{arquivo_id} {nome}: {len(mapa):,} registros', flush=True)
    mapa = pd.concat(mapas)
    colunas = ['registro_id', 'registro_id_novo', 'arquivo_id', 'arquivo_origem', 'linha_origem', 'linha_nova',
               'registro_original_sha256', 'tribunal', 'avaliacao']
    mapa[colunas].rename(columns={'registro_id': 'registro_id_base_completa', 'linha_origem': 'linha_base_completa'}) \
        .to_parquet(RELATORIO / 'mapa_registro_id.parquet', index=False)
    estratos.to_csv(RELATORIO / 'estratos_tst.csv', index=False, encoding='utf-8-sig')
    manifesto = dict(
        protocolo='jurisprudencia-base-reduzida-opcao-d-v1', criado_em_utc=datetime.now(timezone.utc).isoformat(),
        criterios=dict(
            ponto_de_partida='candidato_consolidado do notebook 03 (base completa)',
            A='um documento por processo (grupo_processo); mantém o maior texto; registros sem processo são mantidos',
            B=f'TST limitado a {LIMITE_TST:,} por amostragem estratificada proporcional (ano x órgão julgador)',
            demais_tribunais='TRT-10, TRT-13, TRT-17 e STF trabalhista mantidos após A',
            arquivos_sem_candidatos='mantidos no inventário somente com o critério A; continuam fora do recorte de candidatos ao RAG',
            avaliacao=f'{n_aval} registros dos gabaritos, da curadoria e dos experimentos do notebook 04 incluídos obrigatoriamente '
                      '(reports/jurisprudencia/base_reduzida/ids_obrigatorios.json)', seed=SEED),
        etapas=etapas, registros=len(sel), por_tribunal=sel.tribunal.value_counts().to_dict(),
        arquivo_excluido='train-00002.parquet (ilegível na base completa; sem registros)',
        arquivos=arquivos, pasta=str(SAIDA.relative_to(ROOT)),
        mapa_ids=str((RELATORIO / 'mapa_registro_id.parquet').relative_to(ROOT)),
        nota='Os registro_id mudam porque dependem do hash do arquivo e da linha; use o mapa para converter gabaritos.')
    audit.write_json(RELATORIO / 'manifesto_base_reduzida.json', manifesto)
    print('Total:', len(sel), '| por tribunal:', manifesto['por_tribunal'])


if __name__ == '__main__':
    main()
