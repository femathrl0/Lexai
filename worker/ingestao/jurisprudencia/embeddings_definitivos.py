"""Vetorização incremental do corpus validado, com vínculo verificável vetor/chunk."""
from pathlib import Path
import json,sqlite3,time
import numpy as np
import pyarrow as pa,pyarrow.parquet as pq
from . import audit,chunking_definitivo as chunks,embeddings_backbone as backbone


def validate_vectors(vectors,count):
    v=np.asarray(vectors)
    if v.shape!=(count,1024) or v.dtype!=np.dtype('float32'):raise ValueError('Quantidade, dimensão ou dtype incompatível.')
    if not np.isfinite(v).all() or not np.allclose(np.linalg.norm(v,axis=1),1,atol=1e-4):raise ValueError('Vetor não finito ou sem normalização L2.')


def vector_sha(vector):return audit.digest(np.asarray(vector,dtype='<f4').tobytes())


def mapping_for(rows,vectors):
    validate_vectors(vectors,len(rows))
    if len({r['chunk_id'] for r in rows})!=len(rows):raise ValueError('ID de chunk repetido no lote.')
    out=[]
    for i,(r,v) in enumerate(zip(rows,vectors,strict=True)):
        if chunks.base.sha(r['texto'])!=r['texto_sha256']:raise ValueError('Texto do chunk divergente.')
        if r['tokens']>500 or r['tokens_com_especiais']>502:raise ValueError('Chunk fora da decisão de tamanho.')
        out.append(dict(row_index=i,chunk_id=r['chunk_id'],registro_id=r['registro_id'],texto_sha256=r['texto_sha256'],vector_sha256=vector_sha(v)))
    return out


def validate_mapping(rows,vectors,mapping,cache=None):
    expected=mapping_for(rows,vectors)
    if expected!=mapping:raise ValueError('Ordem ou correspondência vetor/chunk alterada.')
    if cache is not None:
        for r,v in zip(rows,vectors,strict=True):
            found=cache.execute('SELECT vector FROM embeddings WHERE hash=?',(r['texto_sha256'],)).fetchone()
            if found is None or found[0]!=np.asarray(v,dtype='<f4').tobytes():raise ValueError('Vetor não corresponde ao texto no cache do backbone.')


def prepare(root,device='cpu'):
    root=Path(root).resolve()
    from .chunking_definitivo_relatorio import load
    previous=load(root);donepath=previous['report']/'concluido.json';manifest=previous['report']/'manifesto_lotes.json'
    if not donepath.exists() or not manifest.exists():raise ValueError('Notebook 05 ainda não concluiu a auditoria global.')
    done=json.loads(donepath.read_text(encoding='utf-8'))
    if done['status']!='chunking_validado' or done['documentos_restantes']!=0:raise ValueError('Corpus do notebook 05 não está validado.')
    batches=json.loads(manifest.read_text(encoding='utf-8'))
    if batches['configuracao_sha256']!=previous['identity'] or sum(b['chunks'] for b in batches['lotes'])!=done['chunks']:
        raise ValueError('Manifesto e contagem do corpus divergentes.')
    fp=backbone.fingerprint(device);fphash=chunks.canonical(fp)
    if fp['tokenizador_sha256']!=previous['config']['tokenizador_sha256']:raise ValueError('Tokenizador diferente do usado no chunking.')
    # Vetores gerados externamente (GPU do Kaggle, FP16 com salvaguardas) e importados no cache.
    imported=root/'dados/relatorios/jurisprudencia/embeddings/importacao_kaggle.json';origin=None
    if imported.exists():
        info=json.loads(imported.read_text(encoding='utf-8'))
        if info['corpus_chunking']!=previous['identity'] or info['textos_com_vetor']!=info['textos_unicos_corpus']:
            raise ValueError('Importação do Kaggle feita para outro corpus ou incompleta.')
        origin=dict(arquivo=str(imported.relative_to(root)),sha256=audit.hash_file(imported),origem=info['origem'],
            precisao_calculo=info['precisao_calculo'],armazenamento=info['armazenamento'],
            tolerancia_fp16=info['tolerancia_fp16'],cosseno_min_amostra_fp32=info['cosseno_min_amostra_fp32'])
    config=dict(versao=1,corpus_chunking=previous['identity'],manifesto_chunking_arquivo=str(manifest.relative_to(root)),
        manifesto_chunking_sha256=audit.hash_file(manifest),conclusao_chunking_sha256=audit.hash_file(donepath),
        chunks_esperados=done['chunks'],documentos=done['documentos_processados'],
        backbone=fp,backbone_sha256=fphash,batch_size=8,codigo_sha256=audit.hash_file(__file__),
        codigo_backbone_sha256=audit.hash_file(backbone.__file__),
        codigo_pgvector_sha256=audit.hash_file(root/'src/storage/jurisprudencia_pgvector.py'),pgvector_esquema='lex_jurisprudencia',
        origem_vetores=origin,
        politica=('Vetores densos normalizados, gravados em float32; calculados na GPU do Kaggle em FP16 (autocast), com conferência por amostra em float32 e importados no cache.'
                  if origin else 'Gerar vetores densos normalizados, em float32.')+' Sem truncamento, RRF, reranker ou LLM. Legislação não é regravada.')
    identity=chunks.canonical(config);report=root/'dados/relatorios/jurisprudencia/embeddings'/identity;data=root/'indexes/jurisprudencia/embeddings'/identity
    report.mkdir(parents=True,exist_ok=True);data.mkdir(parents=True,exist_ok=True)
    path=report/'configuracao.json'
    if path.exists():
        if json.loads(path.read_text(encoding='utf-8'))!=config:raise ValueError('Versão de embeddings divergente.')
    else:chunks.atomic_json(path,config)
    chunks.atomic_json(root/'dados/relatorios/jurisprudencia/embeddings/ativa.json',dict(pasta_relatorios=str(report.relative_to(root)),pasta_dados=str(data.relative_to(root)),identidade=identity))
    return dict(root=root,report=report,data=data,batches=batches['lotes'],config=config,identity=identity)


def load_cache(state):
    folder=state['root']/'indexes/jurisprudencia/embeddings/cache'/state['config']['backbone_sha256']
    folder.mkdir(parents=True,exist_ok=True);db=sqlite3.connect(folder/'vetores.sqlite')
    db.execute('CREATE TABLE IF NOT EXISTS embeddings(hash TEXT PRIMARY KEY,vector BLOB NOT NULL)')
    return db


def progress(state):
    done=[json.loads(p.read_text(encoding='utf-8')) for p in state['report'].glob('lote_*.json')]
    n=sum(p['chunks'] for p in done)
    result=dict(status='embeddings_gerados' if n==state['config']['chunks_esperados'] else 'embeddings_em_andamento',
        chunks_esperados=state['config']['chunks_esperados'],chunks_vetorizados=n,chunks_restantes=state['config']['chunks_esperados']-n,
        lotes_concluidos=len(done),lotes_esperados=len(state['batches']),indexacao_pgvector_concluida=False)
    chunks.atomic_json(state['report']/'progresso.json',result);return result


def run(root,device='cpu',max_lotes=None):
    state=prepare(root,device)
    with chunks.writer_lock(state['data']):return _run(state,max_lotes)


def _run(state,max_lotes):
    model=backbone.load_model(state['config']['backbone']['device'])
    compatible=backbone.check_legislation(state['root'],model)
    chunks.atomic_json(state['report']/'compatibilidade_legislacao.json',compatible)
    db=load_cache(state);processed=0;start=time.monotonic()
    try:
        for b in state['batches']:
            name=f"{b['arquivo_id']}_{b['batch']:06}";checkpoint=state['report']/('lote_'+name+'.json')
            inputfile=state['root']/b['chunks_arquivo']
            if audit.hash_file(inputfile)!=b['chunks_sha256']:raise ValueError('Chunks de entrada alterados após a auditoria.')
            rows=pq.read_table(inputfile).to_pylist()
            if checkpoint.exists():
                saved=json.loads(checkpoint.read_text(encoding='utf-8'))
                if saved['configuracao_sha256']!=state['identity'] or saved['chunks_entrada_sha256']!=b['chunks_sha256']:raise ValueError('Checkpoint de outro corpus/backbone.')
                vpath=state['root']/saved['vetores_arquivo'];mpath=state['root']/saved['mapeamento_arquivo']
                if audit.hash_file(vpath)!=saved['vetores_sha256'] or audit.hash_file(mpath)!=saved['mapeamento_sha256']:raise ValueError('Saída de embedding alterada.')
                validate_mapping(rows,np.load(vpath,allow_pickle=False),pq.read_table(mpath).to_pylist(),db)
                continue
            unique={r['texto_sha256']:r['texto'] for r in rows}
            missing=[h for h in unique if db.execute('SELECT 1 FROM embeddings WHERE hash=?',(h,)).fetchone() is None]
            generated=0
            for i in range(0,len(missing),8):
                keys=missing[i:i+8];texts=[unique[h] for h in keys]
                if any(len(model.tokenizer.encode(t,add_special_tokens=True,truncation=False,verbose=False))>502 for t in texts):
                    raise ValueError('Limite de tokens não corresponde ao arquivo de chunks.')
                vectors=np.asarray(model.encode(texts,batch_size=8,normalize_embeddings=True,convert_to_numpy=True,show_progress_bar=False),dtype=np.float32)
                validate_vectors(vectors,len(keys))
                with db:db.executemany('INSERT INTO embeddings VALUES(?,?)',[(h,np.asarray(v,dtype='<f4').tobytes()) for h,v in zip(keys,vectors,strict=True)])
                generated+=len(keys)
                if generated%80<8:
                    chunks.atomic_json(state['report']/'progresso_lote.json',dict(lote=name,entradas_novas_concluidas=generated,entradas_novas_total=len(missing),segundos=time.monotonic()-start))
            vectors=np.stack([np.frombuffer(db.execute('SELECT vector FROM embeddings WHERE hash=?',(r['texto_sha256'],)).fetchone()[0],dtype='<f4') for r in rows])
            mapping=mapping_for(rows,vectors);validate_mapping(rows,vectors,mapping,db)
            vpath=state['data']/('vetores_'+name+'.npy');mpath=state['data']/('mapeamento_'+name+'.parquet')
            temp=vpath.with_suffix('.partial.npy');np.save(temp,vectors,allow_pickle=False);chunks.privacy.replace_completed(temp,vpath)
            temp=mpath.with_suffix('.partial.parquet');pq.write_table(pa.Table.from_pylist(mapping),temp,compression='zstd');chunks.privacy.replace_completed(temp,mpath)
            chunks.atomic_json(checkpoint,dict(configuracao_sha256=state['identity'],chunks=len(rows),chunks_entrada_arquivo=b['chunks_arquivo'],
                chunks_entrada_sha256=b['chunks_sha256'],vetores_arquivo=str(vpath.relative_to(state['root'])),vetores_sha256=audit.hash_file(vpath),
                mapeamento_arquivo=str(mpath.relative_to(state['root'])),mapeamento_sha256=audit.hash_file(mpath),
                textos_novos_codificados=len(missing),textos_cache_reutilizados=len(unique)-len(missing)))
            processed+=1;p=progress(state)
            print('Embeddings:',name,p['chunks_vetorizados'],'/',p['chunks_esperados'],flush=True)
            if max_lotes is not None and processed>=max_lotes:return state,p
        result=progress(state)
        if result['chunks_restantes']!=0:raise ValueError('Corpus de embeddings incompleto.')
        files=[json.loads(p.read_text(encoding='utf-8')) for p in sorted(state['report'].glob('lote_*.json'))]
        chunks.atomic_json(state['report']/'manifesto_embeddings.json',dict(configuracao_sha256=state['identity'],lotes=files))
        chunks.atomic_json(state['report']/'concluido.json',dict(result,status='embeddings_validados',compatibilidade_legislacao=compatible['status']))
        return state,result
    finally:db.close()
