"""Exporta o corpus validado do notebook 05 em pacotes para gerar embeddings na GPU do Kaggle.

Formato esperado pelo notebook output/kaggle/06_embeddings_gpu_kaggle.ipynb:
  output/kaggle/pacotes/<job_id>/manifesto_job.json
  output/kaggle/pacotes/<job_id>/partes/<parte_id>.parquet
Cada parte corresponde a um lote do chunking definitivo, com somente as colunas necessárias ao embedding
(chunk_id, registro_id, texto, texto_sha256). Metadados processuais, nomes de relatores e datas não são
exportados. Cada pacote tem no máximo 100.000 chunks (limite do notebook do Kaggle).

Exige o estado `chunking_validado` do notebook 05. A pasta inteira de pacotes deve ser enviada como um
único Kaggle Dataset **privado**; o texto dos chunks pode conter dados pessoais (não é anonimizado).

Uso: python scripts/exportar_pacotes_kaggle_jurisprudencia.py [--reaproveitar output/kaggle/resultados]

Com --reaproveitar, os chunks cujo texto (texto_sha256) já tem vetor em resultados anteriores do Kaggle,
conferidos pelos hashes dos checkpoints, ficam fora dos pacotes; o importador combina os dois conjuntos.
"""
from pathlib import Path
from datetime import datetime, timezone
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from worker.ingestao.jurisprudencia import audit  # noqa: E402

LIMITE = 100_000
COLUNAS = ['chunk_id', 'registro_id', 'texto', 'texto_sha256']
SAIDA = ROOT / 'dados/output/kaggle/pacotes'


def textos_vetorizados(pasta):
    """texto_sha256 com vetor em resultados anteriores, somente de partes com checkpoint e hashes conferidos."""
    import pyarrow.parquet as pq
    conhecidos = set()
    for cp in Path(pasta).rglob('checkpoint_*.json'):
        c = json.loads(cp.read_text(encoding='utf-8'))
        mapeamento, vetores = cp.parent / c['mapeamento_arquivo'], cp.parent / c['vetores_arquivo']
        if audit.hash_file(mapeamento) != c['mapeamento_sha256'] or audit.hash_file(vetores) != c['vetores_sha256']:
            raise RuntimeError(f'Resultado anterior alterado: {cp}')
        conhecidos.update(pq.read_table(mapeamento, columns=['texto_sha256']).column(0).to_pylist())
    return conhecidos


def main():
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq
    sys.stdout.reconfigure(encoding='utf-8')
    conhecidos = textos_vetorizados(ROOT / sys.argv[sys.argv.index('--reaproveitar') + 1]) if '--reaproveitar' in sys.argv else set()
    if conhecidos:
        print(f'Textos já vetorizados reaproveitados: {len(conhecidos):,}', flush=True)
    ponteiro = json.loads((ROOT / 'dados/relatorios/jurisprudencia/chunking_definitivo/ativa.json').read_text(encoding='utf-8'))
    relatorio = ROOT / ponteiro['pasta_relatorios']
    concluido = json.loads((relatorio / 'concluido.json').read_text(encoding='utf-8'))
    if concluido['status'] != 'chunking_validado' or concluido['documentos_restantes'] != 0:
        raise RuntimeError('O chunking do notebook 05 ainda não está validado.')
    lotes = json.loads((relatorio / 'manifesto_lotes.json').read_text(encoding='utf-8'))
    if lotes['configuracao_sha256'] != ponteiro['identidade'] or sum(b['chunks'] for b in lotes['lotes']) != concluido['chunks']:
        raise RuntimeError('Manifesto de lotes divergente da conclusão do chunking.')
    modelo = json.loads((ROOT / 'dados/relatorios/jurisprudencia/embeddings/preflight.json').read_text(encoding='utf-8'))['backbone']
    # Tabelas filtradas por lote (somente textos ainda sem vetor), lidas uma vez e conferidas pelo hash.
    tabelas, reaproveitados = {}, 0
    for b in lotes['lotes']:
        origem = ROOT / b['chunks_arquivo']
        if audit.hash_file(origem) != b['chunks_sha256']:
            raise RuntimeError(f'Chunks alterados após a validação: {origem.name}')
        tabela = pq.read_table(origem, columns=COLUNAS)
        if tabela.num_rows != b['chunks']:
            raise RuntimeError(f'Contagem divergente em {origem.name}.')
        if conhecidos:
            novos = tabela.filter(pc.invert(pc.is_in(tabela['texto_sha256'], value_set=pa.array(sorted(conhecidos)))))
            reaproveitados += tabela.num_rows - novos.num_rows
            tabela = novos
        if tabela.num_rows:
            tabelas[(b['arquivo_id'], b['batch'])] = (b, tabela)
    jobs, atual = [], []
    for b, tabela in tabelas.values():
        if atual and sum(t.num_rows for _, t in atual) + tabela.num_rows > LIMITE:
            jobs.append(atual)
            atual = []
        atual.append((b, tabela))
    if atual:
        jobs.append(atual)
    if SAIDA.exists() and any(SAIDA.iterdir()):
        raise RuntimeError(f'{SAIDA} já contém pacotes; mova-os antes de exportar outra versão.')
    SAIDA.mkdir(parents=True, exist_ok=True)
    resumo = []
    for n, grupo in enumerate(jobs):
        job_id = f'job_{n:04d}'
        pasta = SAIDA / job_id / 'partes'
        pasta.mkdir(parents=True, exist_ok=True)
        partes = []
        for b, tabela in grupo:
            parte_id = f"{b['arquivo_id']}_{b['batch']:06d}"
            destino = pasta / f'{parte_id}.parquet'
            temporario = destino.with_suffix('.partial.parquet')
            pq.write_table(tabela, temporario, compression='zstd')
            temporario.replace(destino)
            partes.append(dict(parte_id=parte_id, arquivo=f'partes/{destino.name}', sha256=audit.hash_file(destino),
                               chunks=tabela.num_rows, origem_chunks_sha256=b['chunks_sha256']))
        manifesto = dict(job_id=job_id, corpus_validado=True, corpus_chunking=ponteiro['identidade'],
                         modelo=modelo['modelo'], revisao=modelo['revisao'], modelo_arquivos_sha256=modelo['arquivos_sha256'],
                         chunks_total=sum(p['chunks'] for p in partes), colunas=COLUNAS, partes=partes,
                         criado_em_utc=datetime.now(timezone.utc).isoformat(),
                         aviso='Texto não anonimizado integralmente; manter o Kaggle Dataset privado.')
        audit.write_json(SAIDA / job_id / 'manifesto_job.json', manifesto)
        resumo.append(dict(job_id=job_id, partes=len(partes), chunks=manifesto['chunks_total'],
                           manifesto_sha256=audit.hash_file(SAIDA / job_id / 'manifesto_job.json')))
        print(f"{job_id}: {len(partes)} partes, {manifesto['chunks_total']:,} chunks", flush=True)
    total = sum(r['chunks'] for r in resumo)
    if total + reaproveitados != concluido['chunks']:
        raise RuntimeError('Total exportado mais reaproveitado diferente do corpus validado.')
    audit.write_json(SAIDA / 'resumo_pacotes.json', dict(corpus_chunking=ponteiro['identidade'], jobs=resumo,
                     chunks_total=total, chunks_reaproveitados=reaproveitados, chunks_corpus=concluido['chunks'],
                     limite_por_job=LIMITE))
    print(f'Chunks com vetor reaproveitado: {reaproveitados:,}')
    tamanho = sum(p.stat().st_size for p in SAIDA.rglob('*') if p.is_file())
    print(f'{len(resumo)} pacotes, {total:,} chunks, {tamanho / 1e9:.2f} GB em {SAIDA}')


if __name__ == '__main__':
    main()
