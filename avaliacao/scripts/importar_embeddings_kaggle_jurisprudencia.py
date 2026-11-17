"""Importa e valida os embeddings gerados no Kaggle para o corpus ativo do notebook 05.

Para cada parte baixada em output/kaggle/resultados/ (checkpoint_*.json), confere os hashes dos arquivos,
a forma (n, 1024), dtype float32, valores finitos, norma L2 = 1 e o hash de cada vetor no mapeamento.
Exige que todo texto (texto_sha256) dos chunks do corpus validado tenha vetor e grava esses vetores no
cache local usado por src/jurisprudencia/embeddings_definitivos.py, que então monta os lotes do notebook
06 sem recalcular. Registra a origem (Kaggle, FP16 com salvaguardas) em
reports/jurisprudencia/embeddings/importacao_kaggle.json.

Uso: python scripts/importar_embeddings_kaggle_jurisprudencia.py
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
import sys

import numpy as np
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from worker.ingestao.jurisprudencia import audit, chunking_definitivo as chunks, embeddings_backbone as backbone  # noqa: E402

RESULTADOS = ROOT / 'dados/output/kaggle/resultados'
TOLERANCIA = 0.9995


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    ponteiro = json.loads((ROOT / 'dados/relatorios/jurisprudencia/chunking_definitivo/ativa.json').read_text(encoding='utf-8'))
    relatorio = ROOT / ponteiro['pasta_relatorios']
    concluido = json.loads((relatorio / 'concluido.json').read_text(encoding='utf-8'))
    if concluido['status'] != 'chunking_validado':
        raise RuntimeError('Corpus do notebook 05 não validado.')
    lotes = json.loads((relatorio / 'manifesto_lotes.json').read_text(encoding='utf-8'))['lotes']
    necessarios = set()
    for b in lotes:
        if audit.hash_file(ROOT / b['chunks_arquivo']) != b['chunks_sha256']:
            raise RuntimeError(f"Chunks alterados: {b['chunks_arquivo']}")
        necessarios.update(pq.read_table(ROOT / b['chunks_arquivo'], columns=['texto_sha256']).column(0).to_pylist())
    vetores, origem, cossenos, partes, divergencias = {}, {}, [], 0, 0
    vistos = set()
    for cp in sorted(RESULTADOS.rglob('checkpoint_*.json')):
        c = json.loads(cp.read_text(encoding='utf-8'))
        vf, mf = cp.parent / c['vetores_arquivo'], cp.parent / c['mapeamento_arquivo']
        if c['vetores_sha256'] in vistos:
            continue  # Mesma parte copiada em mais de uma pasta de resultados.
        if audit.hash_file(vf) != c['vetores_sha256'] or audit.hash_file(mf) != c['mapeamento_sha256']:
            raise RuntimeError(f'Arquivo de resultado alterado: {cp}')
        vistos.add(c['vetores_sha256'])
        vv = np.load(vf, allow_pickle=False)
        mm = pq.read_table(mf).to_pylist()
        if vv.shape != (len(mm), 1024) or vv.dtype != np.float32 or not np.isfinite(vv).all():
            raise RuntimeError(f'Forma, dtype ou valores inválidos: {vf.name}')
        if not np.allclose(np.linalg.norm(vv, axis=1), 1, atol=1e-4):
            raise RuntimeError(f'Vetores sem normalização L2: {vf.name}')
        if c.get('cosseno_min_amostra_fp32', 1.0) < TOLERANCIA:
            raise RuntimeError(f'Parte abaixo da tolerância FP16: {cp.name}')
        cossenos.append(c.get('cosseno_min_amostra_fp32'))
        for i, m in enumerate(mm):
            if m['row_index'] != i or hashlib.sha256(np.asarray(vv[i], dtype='<f4').tobytes()).hexdigest() != m['vector_sha256']:
                raise RuntimeError(f'Mapeamento vetor/chunk inconsistente: {mf.name}')
            h = m['texto_sha256']
            if h in vetores:
                if float(np.dot(vetores[h], vv[i])) < TOLERANCIA:
                    divergencias += 1
                continue
            vetores[h] = np.asarray(vv[i], dtype='<f4')
            origem[h] = str(cp.parent.relative_to(RESULTADOS)).replace('\\', '/')
        partes += 1
    if divergencias:
        raise RuntimeError(f'{divergencias} textos com vetores divergentes entre sessões.')
    faltando = necessarios - set(vetores)
    if faltando:
        raise RuntimeError(f'{len(faltando)} textos do corpus sem vetor nos resultados do Kaggle.')
    fp = backbone.fingerprint('cpu')
    cache_dir = ROOT / 'indexes/jurisprudencia/embeddings/cache' / chunks.canonical(fp)
    cache_dir.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(cache_dir / 'vetores.sqlite')
    db.execute('CREATE TABLE IF NOT EXISTS embeddings(hash TEXT PRIMARY KEY,vector BLOB NOT NULL)')
    inseridos = 0
    with db:
        for h in sorted(necessarios):
            antigo = db.execute('SELECT vector FROM embeddings WHERE hash=?', (h,)).fetchone()
            if antigo is None:
                db.execute('INSERT INTO embeddings VALUES(?,?)', (h, vetores[h].tobytes()))
                inseridos += 1
            elif float(np.dot(np.frombuffer(antigo[0], dtype='<f4'), vetores[h])) < TOLERANCIA:
                raise RuntimeError('Vetor já existente no cache diverge do importado.')
    total_cache = db.execute('SELECT COUNT(*) FROM embeddings').fetchone()[0]
    db.close()
    por_origem = {}
    for h in necessarios:
        por_origem[origem[h].split('/')[0]] = por_origem.get(origem[h].split('/')[0], 0) + 1
    manifesto = dict(
        protocolo='jurisprudencia-importacao-embeddings-kaggle-v1', criado_em_utc=datetime.now(timezone.utc).isoformat(),
        corpus_chunking=ponteiro['identidade'], chunks_corpus=concluido['chunks'], textos_unicos_corpus=len(necessarios),
        textos_com_vetor=len(necessarios), textos_por_sessao=por_origem, partes_conferidas=partes,
        origem='GPU NVIDIA T4 no Kaggle (notebook output/kaggle/06_embeddings_gpu_kaggle.ipynb)',
        precisao_calculo='fp16_autocast', armazenamento='float32_renormalizado', tolerancia_fp16=TOLERANCIA,
        cosseno_min_amostra_fp32=min(cossenos), modelo=fp['modelo'], revisao=fp['revisao'],
        cache=str((cache_dir / 'vetores.sqlite').relative_to(ROOT)), vetores_inseridos_no_cache=inseridos,
        vetores_no_cache=total_cache,
        nota='Vetores conferidos por hash, forma, norma e mapeamento; nenhum texto do corpus ficou sem vetor.')
    audit.write_json(ROOT / 'dados/relatorios/jurisprudencia/embeddings/importacao_kaggle.json', manifesto)
    print(f'Partes conferidas: {partes} | textos do corpus: {len(necessarios):,} | por sessão: {por_origem}')
    print(f'Cache: {inseridos:,} vetores inseridos ({total_cache:,} no total) | cosseno mínimo da amostra: {min(cossenos):.6f}')


if __name__ == '__main__':
    main()
