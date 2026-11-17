"""Coleção própria de jurisprudência; preserva tabelas e vetores de legislação."""
from pathlib import Path
import json
import numpy as np
import pyarrow.parquet as pq
from worker.ingestao.jurisprudencia import audit,chunking_definitivo as chunks,embeddings_definitivos as emb
from .pgvector_store import load_database_url

DDL='''
CREATE SCHEMA IF NOT EXISTS lex_jurisprudencia;
CREATE TABLE IF NOT EXISTS lex_jurisprudencia.datasets(
 dataset_id text PRIMARY KEY, chunks_esperados bigint NOT NULL, manifesto jsonb NOT NULL,
 estado text NOT NULL DEFAULT 'em_andamento', atualizado_em timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS lex_jurisprudencia.embeddings(
 dataset_id text NOT NULL REFERENCES lex_jurisprudencia.datasets(dataset_id),
 chunk_id text NOT NULL, registro_id text NOT NULL, texto text NOT NULL,
 texto_sha256 text NOT NULL, vetor_sha256 text NOT NULL, metadata jsonb NOT NULL,
 embedding vector(1024) NOT NULL, PRIMARY KEY(dataset_id,chunk_id));
CREATE TABLE IF NOT EXISTS lex_jurisprudencia.lotes(
 dataset_id text NOT NULL REFERENCES lex_jurisprudencia.datasets(dataset_id),
 lote text NOT NULL, vetor_arquivo_sha256 text NOT NULL, chunks bigint NOT NULL,
 PRIMARY KEY(dataset_id,lote));
'''


def verify_stored(row,mapping,stored):
    ident,parent,text_hash,vec_hash,vector,text,metadata=stored
    # O pgvector-python pode devolver um objeto Vector; o hash é calculado sobre os float32 lidos do banco.
    vector=np.asarray(vector.to_numpy() if hasattr(vector,'to_numpy') else vector,dtype='<f4')
    if (ident!=row['chunk_id'] or parent!=row['registro_id'] or text_hash!=row['texto_sha256']
        or vec_hash!=mapping['vector_sha256'] or emb.vector_sha(vector)!=mapping['vector_sha256']
        or text!=row['texto'] or metadata!={k:v for k,v in row.items() if k!='texto'}):
        raise ValueError('Correspondência de texto, metadados ou vetor divergiu no banco.')


def import_verified(state):
    import psycopg
    from psycopg.types.json import Jsonb
    from pgvector.psycopg import register_vector
    done=state['report']/'concluido.json';manifest=state['report']/'manifesto_embeddings.json'
    if not done.exists() or json.loads(done.read_text(encoding='utf-8'))['status']!='embeddings_validados':
        raise ValueError('Embeddings completos e validados são necessários antes da importação.')
    if audit.hash_file(__file__)!=state['config']['codigo_pgvector_sha256']:raise ValueError('Código de importação mudou após congelar a versão de embeddings.')
    batchlist=json.loads(manifest.read_text(encoding='utf-8'))['lotes']
    dataset=state['identity'];expected=state['config']['chunks_esperados']
    try:connection=psycopg.connect(load_database_url(state['root']/'.env.pgvector.local'),connect_timeout=8,autocommit=True)
    except Exception as e:raise RuntimeError('Banco indisponível para jurisprudência; tipo='+type(e).__name__) from None
    try:
        with connection.transaction():
            if not connection.execute("SELECT 1 FROM pg_extension WHERE extname='vector'").fetchone():raise RuntimeError('Extensão pgvector não está disponível.')
            register_vector(connection);connection.execute(DDL)
            connection.execute('INSERT INTO lex_jurisprudencia.datasets(dataset_id,chunks_esperados,manifesto) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING',
                (dataset,expected,Jsonb(state['config'])))
            saved=connection.execute('SELECT chunks_esperados,manifesto FROM lex_jurisprudencia.datasets WHERE dataset_id=%s',(dataset,)).fetchone()
            if saved[0]!=expected or saved[1]!=state['config']:raise ValueError('Dataset de banco com configuração divergente.')
        for batch in batchlist:
            inputfile=state['root']/batch['chunks_entrada_arquivo'];vfile=state['root']/batch['vetores_arquivo'];mfile=state['root']/batch['mapeamento_arquivo']
            for path,sha in [(inputfile,batch['chunks_entrada_sha256']),(vfile,batch['vetores_sha256']),(mfile,batch['mapeamento_sha256'])]:
                if audit.hash_file(path)!=sha:raise ValueError('Artefato alterado antes da importação.')
            rows=pq.read_table(inputfile).to_pylist();vectors=np.load(vfile,allow_pickle=False);mapping=pq.read_table(mfile).to_pylist()
            emb.validate_mapping(rows,vectors,mapping);label=vfile.stem
            with connection.transaction():
                checkpoint=connection.execute('SELECT vetor_arquivo_sha256,chunks FROM lex_jurisprudencia.lotes WHERE dataset_id=%s AND lote=%s',(dataset,label)).fetchone()
                if checkpoint and checkpoint!=(batch['vetores_sha256'],len(rows)):raise ValueError('Lote do banco divergente.')
                if checkpoint is None:
                    values=[(dataset,r['chunk_id'],r['registro_id'],r['texto'],r['texto_sha256'],m['vector_sha256'],
                             Jsonb({k:v for k,v in r.items() if k!='texto'}),v) for r,m,v in zip(rows,mapping,vectors,strict=True)]
                    with connection.cursor() as cursor:
                        cursor.executemany('INSERT INTO lex_jurisprudencia.embeddings VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',values)
                retrieved=connection.execute('SELECT chunk_id,registro_id,texto_sha256,vetor_sha256,embedding,texto,metadata FROM lex_jurisprudencia.embeddings WHERE dataset_id=%s AND chunk_id=ANY(%s)',
                    (dataset,[r['chunk_id'] for r in rows])).fetchall()
                stored={r[0]:r for r in retrieved}
                if len(stored)!=len(rows):raise ValueError('Lote incompleto no banco.')
                for r,m in zip(rows,mapping,strict=True):
                    verify_stored(r,m,stored[r['chunk_id']])
                connection.execute('INSERT INTO lex_jurisprudencia.lotes VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING',(dataset,label,batch['vetores_sha256'],len(rows)))
            chunks.atomic_json(state['report']/'progresso_pgvector.json',dict(ultimo_lote=label,chunks_lote=len(rows),estado='importando'))
            print('pgvector:',label,len(rows),'chunks verificados',flush=True)
        with connection.transaction():
            count=connection.execute('SELECT count(*) FROM lex_jurisprudencia.embeddings WHERE dataset_id=%s',(dataset,)).fetchone()[0]
            if count!=expected:raise ValueError('Contagem final do banco difere do corpus de embeddings.')
            connection.execute("UPDATE lex_jurisprudencia.datasets SET estado='validado',atualizado_em=now() WHERE dataset_id=%s",(dataset,))
        result=dict(status='indexacao_pgvector_validada',dataset_id=dataset,chunks=count,esquema='lex_jurisprudencia',
            manifesto_embeddings_sha256=audit.hash_file(manifest),tabelas_legislacao_alteradas=False,
            indice_aproximado_criado=False,observacao='Importação e releitura exatas. A avaliação de recuperação e a integração das fontes são etapas posteriores.')
        chunks.atomic_json(state['report']/'pgvector_concluido.json',result);return result
    finally:connection.close()
