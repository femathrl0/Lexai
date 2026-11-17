"""Exporta os 19 Parquets ativos da jurisprudência (etapa PLN leve) para um único JSONL.

A leitura é feita em lotes, sem carregar a base inteira na memória. Os Parquets
de origem não são alterados: o JSONL é uma cópia para compartilhamento, e o
pipeline (chunking e embeddings) continua lendo os Parquets.

Uso:
    python scripts/exportar_jsonl_jurisprudencia.py [--subpasta NOME]

Com --subpasta, grava em data/processed/jurisprudencia/exportacao/NOME/ (ex.: base_reduzida),
sem sobrescrever exportações anteriores.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import sys

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[3]
POINTER = ROOT / 'dados/processed/jurisprudencia/pln_leve/ativa.json'
OUT_DIR = ROOT / 'dados/processed/jurisprudencia/exportacao'
OUT_NAME = 'jurisprudencia_pln_leve.jsonl'
BATCH_SIZE = 2_000
CHUNK = 1 << 20


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(CHUNK), b''):
            h.update(block)
    return h.hexdigest()


def main():
    global OUT_DIR
    sys.stdout.reconfigure(encoding='utf-8')
    if '--subpasta' in sys.argv:
        OUT_DIR = OUT_DIR / sys.argv[sys.argv.index('--subpasta') + 1]
    pointer = json.loads(POINTER.read_text(encoding='utf-8'))
    source_dir = ROOT / pointer['pasta_dados']
    sources = sorted(source_dir.glob('f??.parquet'))
    if len(sources) != 19:
        raise RuntimeError(f'Esperados 19 Parquets ativos, encontrados {len(sources)} em {source_dir}.')
    schema = pq.read_schema(sources[0])
    for p in sources[1:]:
        if not pq.read_schema(p).equals(schema):
            raise RuntimeError(f'Esquema divergente em {p.name}.')

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    final = OUT_DIR / OUT_NAME
    partial = OUT_DIR / (OUT_NAME + '.partial')
    out_hash = hashlib.sha256()
    per_file = []
    total = 0
    with open(partial, 'wb') as out:
        for p in sources:
            expected = pq.ParquetFile(p).metadata.num_rows
            written = 0
            for batch in pq.ParquetFile(p).iter_batches(batch_size=BATCH_SIZE, use_threads=False):
                lines = ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in batch.to_pylist())
                data = lines.encode('utf-8')
                out.write(data)
                out_hash.update(data)
                written += batch.num_rows
            if written != expected:
                raise RuntimeError(f'{p.name}: {written} linhas gravadas, {expected} esperadas.')
            total += written
            per_file.append(dict(arquivo=p.name, registros=written, sha256=sha256_file(p), bytes=p.stat().st_size))
            print(f'{p.name}: {written:,} registros (acumulado {total:,})', flush=True)

    # Releitura independente: conta linhas e valida que cada uma é um JSON válido.
    reread = 0
    with open(partial, 'r', encoding='utf-8') as f:
        for line in f:
            json.loads(line)
            reread += 1
    if reread != total:
        raise RuntimeError(f'Releitura com {reread} linhas; esperado {total}.')
    partial.replace(final)

    manifest = dict(
        protocolo='jurisprudencia-exportacao-jsonl-v1',
        criado_em_utc=datetime.now(timezone.utc).isoformat(),
        origem=dict(etapa='pln_leve', pasta_dados=pointer['pasta_dados'], arquivos=per_file),
        saida=dict(arquivo=str(final.relative_to(ROOT)), formato='JSONL (um registro JSON por linha, UTF-8)',
                   registros=total, bytes=final.stat().st_size, sha256=out_hash.hexdigest(),
                   colunas=schema.names),
        validacao=dict(linhas_relidas=reread, json_valido_em_todas_as_linhas=True),
        nota='Cópia derivada para compartilhamento; os Parquets permanecem como base canônica do pipeline. '
             'CPFs já mascarados na etapa de proteção; não equivale a anonimização integral.',
    )
    (OUT_DIR / 'manifesto_jsonl.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('JSONL:', final)
    print('Registros:', total, '| bytes:', final.stat().st_size, '| sha256:', out_hash.hexdigest())


if __name__ == '__main__':
    main()
