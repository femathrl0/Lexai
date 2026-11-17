"""Verifica backbone local contra vetores de legislação, sem alterar seus artefatos."""
from pathlib import Path
from importlib.metadata import version
import json,time,os
import numpy as np
from . import audit,piloto_bge,chunking_definitivo as chunks


def fingerprint(device='cpu'):
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
    from transformers.utils.hub import cached_file
    from transformers import AutoTokenizer
    snapshot=Path(cached_file(piloto_bge.MODEL,'config.json',revision=piloto_bge.REVISION,local_files_only=True)).parent
    default=Path(cached_file(piloto_bge.MODEL,'config.json',local_files_only=True)).parent
    if snapshot.resolve()!=default.resolve():raise ValueError('O snapshot padrão da legislação difere do snapshot selecionado.')
    names=['config.json','modules.json','config_sentence_transformers.json','sentence_bert_config.json',
           'tokenizer.json','tokenizer_config.json','special_tokens_map.json','sentencepiece.bpe.model','1_Pooling/config.json']
    names += ['model.safetensors' if (snapshot/'model.safetensors').exists() else 'pytorch_model.bin']
    hashes={name:audit.hash_file(snapshot/name) for name in names}
    tokenizer=AutoTokenizer.from_pretrained(piloto_bge.MODEL,revision=piloto_bge.REVISION,local_files_only=True,use_fast=True)
    return dict(modelo=piloto_bge.MODEL,revisao=piloto_bge.REVISION,arquivos_sha256=hashes,
        tokenizador_sha256=chunks.base.sha(tokenizer.backend_tokenizer.to_str()),
        max_seq_length=8192,dimensao=1024,dtype='float32',normalizacao_l2=True,saida='dense',prefixo_adicionado=False,
        device=device,pacotes={name:version(name) for name in ('torch','transformers','sentence-transformers','numpy')})


def load_model(device='cpu'):
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
    import torch
    from sentence_transformers import SentenceTransformer
    torch.set_num_threads(4)
    if device=='cuda' and not torch.cuda.is_available():raise ValueError('CUDA não disponível neste ambiente.')
    if device not in ('cpu','cuda'):raise ValueError('Device não suportado.')
    model=SentenceTransformer(piloto_bge.MODEL,revision=piloto_bge.REVISION,local_files_only=True,device=device)
    model.float();model.max_seq_length=8192
    if model.get_embedding_dimension()!=1024:raise ValueError('Dimensão de backbone incorreta.')
    return model


def check_legislation(root,model):
    from worker.evidencia.indices.pgvector_store import sha256_file,json_hash,vector_hash
    root=Path(root)
    path=root/'dados/relatorios/legislacao/pgvector/D_paragrafo_completo/manifesto_importacao.json'
    manifest=json.loads(path.read_text(encoding='utf-8'))
    textpath=root/'dados/chunks/legislacao/chunks_D_paragrafo_completo.json'
    vectorpath=root/'indexes/legislacao/embeddings'/(manifest['cache_key']+'.npy')
    if sha256_file(textpath)!=manifest['chunks_sha256'] or sha256_file(vectorpath)!=manifest['vectors_sha256']:
        raise ValueError('Artefatos de legislação divergentes do manifesto congelado.')
    texts=json.loads(textpath.read_text(encoding='utf-8'));vectors=np.load(vectorpath,mmap_mode='r',allow_pickle=False)
    if vectors.shape!=(len(texts),1024) or vectors.dtype!=np.dtype('float32'):raise ValueError('Cache de legislação incompatível.')
    mapping=[dict(row_index=i,chunk_id=r['chunk_id'],article_id=r['artigo_id'],
        text_sha256=chunks.base.sha(r['conteudo_chunk']),vector_sha256=vector_hash(vectors[i])) for i,r in enumerate(texts)]
    if json_hash(mapping)!=manifest['ordered_mapping_sha256']:raise ValueError('Ordem de vetores de legislação divergente do manifesto.')
    candidates=[]
    for i,r in enumerate(texts):
        n=len(model.tokenizer.encode(r['conteudo_chunk'],add_special_tokens=False,truncation=False,verbose=False))
        if 8<=n<=80:candidates.append(i)
        if len(candidates)==3:break
    if len(candidates)!=3:raise ValueError('Amostra técnica de compatibilidade indisponível.')
    actual=model.encode([texts[i]['conteudo_chunk'] for i in candidates],normalize_embeddings=True,convert_to_numpy=True,show_progress_bar=False)
    expected=np.asarray(vectors[candidates],dtype=np.float32)
    cosine=np.sum(actual*expected,axis=1);error=float(np.max(np.abs(actual-expected)))
    if not np.isfinite(actual).all() or min(cosine)<.99999 or error>1e-4:raise ValueError('Prova numérica de compatibilidade com legislação falhou.')
    return dict(status='compativel_na_prova_numerica',amostras=3,cosine_min=float(min(cosine)),erro_absoluto_max=error,
        manifesto_legislacao_sha256=sha256_file(path),dataset_legislacao=manifest['dataset_id'],
        indice_cache_legislacao=manifest['cache_key'],corpus_legislacao_regravado=False,
        observacao='Três vetores de prova transitórios; cache e banco de legislação preservados. Artefatos conferidos pelo manifesto original, sem reconstruir sua chave com versões atuais de bibliotecas.')


def database_preflight(root):
    try:
        import psycopg
        from worker.evidencia.indices.pgvector_store import load_database_url
        url=load_database_url(Path(root)/'.env.pgvector.local')
        with psycopg.connect(url,connect_timeout=5) as connection:
            extension=connection.execute("SELECT extversion FROM pg_extension WHERE extname='vector'").fetchone()
        return dict(disponivel=bool(extension),pgvector_versao=extension[0] if extension else None,consulta_somente_leitura=True)
    except Exception as e:
        return dict(disponivel=False,erro_tipo=type(e).__name__,consulta_somente_leitura=True,
                    observacao='Credenciais e texto da exceção não são registrados.')


def preflight(root,device='cpu',benchmark=True):
    root=Path(root);fp=fingerprint(device);model=load_model(device)
    compatibility=check_legislation(root,model)
    result=dict(backbone=fp,backbone_sha256=chunks.canonical(fp),compatibilidade_legislacao=compatibility,
        banco=database_preflight(root),corpus_vetorizado=False)
    if benchmark:
        # Textos artificiais apenas para medir custo; não são gabarito nem avaliação jurídica.
        text=('Texto artificial para medir tempo de processamento de um documento. Não representa decisão judicial. '*500)
        offsets=model.tokenizer(text,add_special_tokens=False,return_offsets_mapping=True,verbose=False)['offset_mapping']
        samples=[text[:offsets[499][1]] for _ in range(8)]
        start=time.monotonic();model.encode(samples,batch_size=8,normalize_embeddings=True,convert_to_numpy=True,show_progress_bar=False)
        seconds=time.monotonic()-start
        result['benchmark']=dict(entradas=8,tokens_texto_por_entrada=500,segundos=seconds,segundos_por_chunk=seconds/8,
            horas_por_milhao_chunks=seconds/8*1_000_000/3600,amostra='artificial; apenas custo computacional')
    folder=root/'dados/relatorios/jurisprudencia/embeddings';folder.mkdir(parents=True,exist_ok=True)
    chunks.atomic_json(folder/'preflight.json',result)
    return result
