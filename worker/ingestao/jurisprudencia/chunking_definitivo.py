"""Chunking da base consolidada por lotes retomáveis, sem embeddings ou LLM."""
from pathlib import Path
from collections import Counter,defaultdict
from contextlib import contextmanager
from datetime import datetime,timezone
import hashlib,json,os,sqlite3,time
import pyarrow as pa
import pyarrow.parquet as pq
from . import audit,automatic_review,light_nlp,chunking,privacy,chunking_suporte as base,piloto_bge

NAME='fixa_500_o100'
BATCH_SIZE=128
CHUNK_INTS={'ordem','inicio','fim','tokens','tokens_com_especiais','sobreposicao_anterior_caracteres',
            'sobreposicao_anterior_tokens','tamanho_alvo_tokens','sobreposicao_alvo_tokens'}
CHUNK_FIELDS=('chunk_id','registro_id','arquivo_id','tribunal','campo_texto','tipo_conteudo_declarado',
    'tipo_conteudo_inferido','ordem','inicio','fim','texto','texto_sha256','texto_base_sha256','tokens',
    'tokens_com_especiais','sobreposicao_anterior_caracteres','sobreposicao_anterior_tokens','estrategia',
    'tamanho_alvo_tokens','sobreposicao_alvo_tokens','tokenizador','tokenizador_revisao','metodo_fronteira',
    'espaco_offsets','parent_arquivo','parent_sha256','grupo_avaliacao','split_proposto','grupo_copia_textual',
    'privacidade_status','processo_cnj','orgao_julgador','relator','classe_origem','tipo_decisao_origem',
    'data_julgamento','data_publicacao','data_assinatura')
CHUNK_SCHEMA=pa.schema([(k,pa.int64() if k in CHUNK_INTS else pa.string()) for k in CHUNK_FIELDS])
DOC_INTS={'caracteres','chunks','tokens_documento','tokens_indexados','tokens_min','tokens_max',
          'sobreposicao_tokens_min','sobreposicao_tokens_max'}
DOC_FIELDS=('registro_id','arquivo_id','tribunal','campo_texto','texto_base_sha256','caracteres','chunks',
    'tokens_documento','tokens_indexados','tokens_min','tokens_max','sobreposicao_tokens_min',
    'sobreposicao_tokens_max','grupo_avaliacao','split_proposto','reconstrucao_aprovada')
DOC_SCHEMA=pa.schema([(k,pa.int64() if k in DOC_INTS else pa.bool_() if k=='reconstrucao_aprovada' else pa.string()) for k in DOC_FIELDS])


def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.partial.json')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    privacy.replace_completed(temp,path)


@contextmanager
def writer_lock(directory):
    path=Path(directory)/'writer.lock'
    with path.open('a+b') as handle:
        if path.stat().st_size==0:handle.write(b'0');handle.flush()
        handle.seek(0)
        if os.name=='nt':
            import msvcrt
            try:msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            except OSError as e:raise RuntimeError('Outra execução já está processando esta versão.') from e
        else:
            import fcntl
            try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError as e:raise RuntimeError('Outra execução já está processando esta versão.') from e
        try:yield
        finally:
            handle.seek(0)
            if os.name=='nt':msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(handle,fcntl.LOCK_UN)


def canonical(value):return base.sha(json.dumps(value,sort_keys=True,ensure_ascii=False))


def within(root,path,folder):
    target=(Path(root)/path).resolve()
    if not target.is_relative_to((Path(root)/folder).resolve()):raise ValueError('Caminho fora da etapa permitida.')
    return target


def document_chunks(doc,meta,source,tokenizer):
    """Mesmo splitter do experimento vencedor; offsets no texto protegido, não no chunk."""
    field=doc['texto_principal_campo']
    if field not in light_nlp.TEXT_FIELDS:raise ValueError('Campo textual principal desconhecido.')
    text=doc[field]
    if not isinstance(text,str) or not text.strip():raise ValueError('Candidato sem texto principal.')
    if len(text)!=meta['texto_caracteres']:raise ValueError('Comprimento diferente do índice de triagem.')
    if privacy.PY_PATTERN.search(text):raise ValueError('CPF residual detectado; conteúdo não exibido.')
    ident=doc['registro_id'];text_hash=base.sha(text)
    masks=[(m.start(),m.end()) for m in chunking.MARKER.finditer(text)]
    rows=[];cursor=0;previous_end=0;covered=[];overlaps=[]
    spans=chunking.split_spans(text,tokenizer,500,100)
    for order,(a,b) in enumerate(spans):
        value=text[a:b];tokens=chunking.token_count(value,tokenizer)
        if not (0<=a<=cursor<b<=len(text) and value.strip() and tokens<=500):raise ValueError('Cobertura ou limite de chunk inválido.')
        if any(x<a<y or x<b<y for x,y in masks):raise ValueError('Marcador de CPF cortado.')
        covered.append(text[cursor:b]);cursor=b
        overlap=max(0,previous_end-a)
        overlap_tokens=chunking.token_count(text[a:previous_end],tokenizer) if overlap else 0
        if order:overlaps.append(overlap_tokens)
        previous_end=b
        row=dict(chunk_id=base.sha('|'.join([NAME,piloto_bge.REVISION,ident,field,text_hash,str(a),str(b)])),
            registro_id=ident,arquivo_id=doc['arquivo_id'],tribunal=doc['tribunal'],
            campo_texto=field,tipo_conteudo_declarado=meta['tipo_conteudo_declarado'],
            tipo_conteudo_inferido=meta['tipo_conteudo_inferido'],
            ordem=order,inicio=a,fim=b,texto=value,texto_sha256=base.sha(value),texto_base_sha256=text_hash,
            tokens=tokens,tokens_com_especiais=tokens+tokenizer.num_special_tokens_to_add(pair=False),
            sobreposicao_anterior_caracteres=overlap,sobreposicao_anterior_tokens=overlap_tokens,
            estrategia=NAME,tamanho_alvo_tokens=500,sobreposicao_alvo_tokens=100,
            tokenizador=piloto_bge.MODEL,tokenizador_revisao=piloto_bge.REVISION,
            metodo_fronteira='tokens_fixos_com_sobreposicao_marcador_cpf_atomico',
            espaco_offsets='documento_base_protegido',parent_arquivo=source['arquivo'],parent_sha256=source['sha256'],
            grupo_avaliacao=meta['grupo_avaliacao'],split_proposto=meta['split_proposto'],
            grupo_copia_textual=meta.get('grupo_copia_textual'),privacidade_status=doc['privacidade_status'])
        for name in ('processo_cnj','orgao_julgador','relator','classe_origem','tipo_decisao_origem',
                     'data_julgamento','data_publicacao','data_assinatura'):
            row[name]=doc.get(name)
        rows.append(row)
    if cursor!=len(text) or ''.join(covered)!=text:raise ValueError('Reconstrução do documento-base falhou.')
    if len({r['chunk_id'] for r in rows})!=len(rows):raise ValueError('Chunk repetido no documento.')
    summary=dict(registro_id=ident,arquivo_id=doc['arquivo_id'],tribunal=doc['tribunal'],campo_texto=field,
        texto_base_sha256=text_hash,caracteres=len(text),chunks=len(rows),tokens_documento=chunking.token_count(text,tokenizer),
        tokens_indexados=sum(r['tokens'] for r in rows),tokens_min=min(r['tokens'] for r in rows),
        tokens_max=max(r['tokens'] for r in rows),sobreposicao_tokens_min=min(overlaps) if overlaps else None,
        sobreposicao_tokens_max=max(overlaps) if overlaps else None,grupo_avaliacao=meta['grupo_avaliacao'],
        split_proposto=meta['split_proposto'],reconstrucao_aprovada=True)
    return rows,summary


def prepare(root):
    root=Path(root).resolve();os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
    from transformers import AutoTokenizer
    auto_dir,auto=automatic_review.load(root);pln_dir,pln=light_nlp.load(root)
    if auto['base_pln_csv_sha256']!=pln['csv_sha256']:raise ValueError('Índice e base PLN são de versões diferentes.')
    index_path=within(root,auto['indice'],'dados/processed/jurisprudencia/automacao')
    if audit.hash_file(index_path)!=auto['indice_sha256']:raise ValueError('Índice de triagem alterado.')
    table=pq.read_table(index_path);all_meta=table.to_pylist()
    metadata={m['registro_id']:m for m in all_meta if m['candidato_consolidado']}
    if len(metadata)!=auto['candidatos_consolidados'] or len(all_meta)!=auto['registros']:raise ValueError('Contagem de candidatos divergente.')
    # Recorte de indexação (amostra estratificada com os documentos dos experimentos), quando definido.
    cut_path=root/'dados/relatorios/jurisprudencia/base_reduzida/recorte_indexacao.json';cut=None
    if cut_path.exists():
        chosen=json.loads(cut_path.read_text(encoding='utf-8'))
        if chosen['indice_sha256']!=auto['indice_sha256']:raise ValueError('Recorte de indexação feito sobre outro índice.')
        ids=set(chosen['registro_ids'])
        if len(ids)!=chosen['documentos'] or not ids<=set(metadata):raise ValueError('Recorte de indexação fora dos candidatos.')
        metadata={k:v for k,v in metadata.items() if k in ids}
        cut=dict(arquivo=str(cut_path.relative_to(root)),sha256=audit.hash_file(cut_path),documentos=len(ids),
                 candidatos_consolidados=auto['candidatos_consolidados'],criterios=chosen['criterios'])
    counts=Counter(m['arquivo_id'] for m in metadata.values())
    sources=[s for s in pln['arquivos'] if s['arquivo_id'] in counts]
    tokenizer=AutoTokenizer.from_pretrained(piloto_bge.MODEL,revision=piloto_bge.REVISION,local_files_only=True,use_fast=True)
    if not tokenizer.is_fast or tokenizer.num_special_tokens_to_add(pair=False)!=2:raise ValueError('Tokenizador incompatível com a decisão.')
    decision_path=root/'notebooks/02_jurisprudencia/04_experimentos_chunking_jurisprudencia.ipynb'
    book=json.loads(decision_path.read_text(encoding='utf-8'))
    decision=next(c for c in book['cells'] if c['id']=='v9_decisao_estrategia_chunking')
    config=dict(versao=1,estrategia=NAME,tamanho_tokens=500,sobreposicao_tokens=100,
        tokenizador=piloto_bge.MODEL,revisao=piloto_bge.REVISION,
        tokenizador_sha256=base.sha(tokenizer.backend_tokenizer.to_str()),
        corpus_entrada=auto['registros'],documentos_esperados=len(metadata),
        caracteres_esperados=sum(m['texto_caracteres'] for m in metadata.values()),
        criterio='candidato_consolidado do índice automático do notebook 03; sem nova triagem por pergunta ou score'
            +('; restrito ao recorte de indexação estratificado' if cut else ''),
        recorte_indexacao=cut,
        campos='Apenas texto_principal_campo de cada documento. Ementa e inteiro teor não são concatenados.',
        particoes='Preservadas como metadados; chunking não é treino nem nova avaliação e não redefine os splits.',
        deduplicacao='Representantes consolidados do notebook 03. Chunks idênticos não são apagados: seus vínculos de origem são preservados.',
        indexacao_vetorial_executada=False,embeddings_gerados=False,modelo_llm_executado=False,
        anonimizacao_integral=False,protecao='CPFs previamente mascarados; verificação residual no texto principal; outros dados pessoais podem permanecer.',
        batch_size=BATCH_SIZE,indice_arquivo=auto['indice'],indice_sha256=auto['indice_sha256'],
        resumo_pln_sha256=audit.hash_file(pln_dir/'resumo_pln.json'),
        resumo_automatico_sha256=audit.hash_file(auto_dir/'resumo_automatico.json'),
        decisao_celula_sha256=canonical(decision),fontes=sources,
        codigo_sha256=audit.hash_file(__file__),splitter_sha256=audit.hash_file(chunking.__file__))
    identity=canonical(config);data=root/'dados/chunks/jurisprudencia/definitivo'/identity;report=root/'dados/relatorios/jurisprudencia/chunking_definitivo'/identity
    data.mkdir(parents=True,exist_ok=True);report.mkdir(parents=True,exist_ok=True)
    path=report/'configuracao.json'
    if path.exists():
        if json.loads(path.read_text(encoding='utf-8'))!=config:raise ValueError('Configuração diferente; não retomar nesta versão.')
    else:audit.write_json(path,config)
    audit.write_json(root/'dados/relatorios/jurisprudencia/chunking_definitivo/ativa.json',dict(pasta_relatorios=str(report.relative_to(root)),pasta_dados=str(data.relative_to(root)),identidade=identity))
    scoped=[]
    for s in sources:
        scoped.append(dict(arquivo_id=s['arquivo_id'],documentos_elegiveis=counts[s['arquivo_id']],
            caracteres=sum(m['texto_caracteres'] for m in metadata.values() if m['arquivo_id']==s['arquivo_id']),
            entrada_sha256=s['sha256']))
    audit.write_csv(report/'escopo_por_arquivo.csv',scoped)
    return dict(root=root,report=report,data=data,metadata=metadata,sources=sources,tokenizer=tokenizer,config=config,identity=identity)


def checkpoints(state):
    out=[]
    for p in sorted(state['report'].glob('lote_*.json')):
        item=json.loads(p.read_text(encoding='utf-8'))
        if item['configuracao_sha256']!=state['identity']:raise ValueError('Checkpoint de outra configuração.')
        out.append(item)
    return out


def status(state):
    parts=checkpoints(state);done=sum(p['documentos'] for p in parts)
    result=dict(status='chunking_gerado_aguardando_verificacao' if done==len(state['metadata']) else 'chunking_em_andamento',
        documentos_esperados=len(state['metadata']),documentos_processados=done,
        documentos_restantes=len(state['metadata'])-done,chunks=sum(p['chunks'] for p in parts),lotes_concluidos=len(parts),
        caracteres_processados=sum(p['caracteres'] for p in parts),caracteres_esperados=state['config']['caracteres_esperados'],
        embeddings_gerados=False,indexacao_vetorial_executada=False,
        atualizado_em_utc=datetime.now(timezone.utc).isoformat())
    atomic_json(state['report']/'progresso.json',result)
    return result


def atomic_parquet(rows,path):
    path=Path(path);temp=path.with_suffix('.partial.parquet')
    schema=CHUNK_SCHEMA if path.name.startswith('chunks_') else DOC_SCHEMA
    pq.write_table(pa.Table.from_pylist(rows,schema=schema),temp,compression='zstd',row_group_size=8192)
    privacy.replace_completed(temp,path)


def run(root,max_lotes=None):
    state=prepare(root)
    with writer_lock(state['data']):return process(state,max_lotes)


def process(state,max_lotes=None):
    start=time.monotonic();done=0
    current=status(state)
    print('Documentos elegíveis:',current['documentos_esperados'],'| concluídos:',current['documentos_processados'],flush=True)
    for source in state['sources']:
        path=within(state['root'],source['arquivo'],'dados/processed/jurisprudencia/pln_leve')
        if audit.hash_file(path)!=source['sha256']:raise ValueError('Fonte protegida alterada.')
        for batch_i,batch in enumerate(pq.ParquetFile(path).iter_batches(batch_size=BATCH_SIZE,use_threads=False)):
            label=f"{source['arquivo_id']}_{batch_i:06}"
            checkpoint=state['report']/('lote_'+label+'.json')
            if checkpoint.exists():
                cp=json.loads(checkpoint.read_text(encoding='utf-8'))
                for name,key in [('chunks','chunks_sha256'),('documentos','documentos_sha256')]:
                    if audit.hash_file(state['root']/cp[name+'_arquivo'])!=cp[key]:raise ValueError('Saída de checkpoint alterada.')
                continue
            rows=[];summaries=[]
            for doc in batch.to_pylist():
                meta=state['metadata'].get(doc['registro_id'])
                if meta is None:continue
                if meta['arquivo_id']!=source['arquivo_id']:raise ValueError('Documento desalinhado com a fonte.')
                chunks,summary=document_chunks(doc,meta,source,state['tokenizer']);rows.extend(chunks);summaries.append(summary)
            if not summaries:continue
            chunks_path=state['data']/('chunks_'+label+'.parquet');docs_path=state['data']/('documentos_'+label+'.parquet')
            atomic_parquet(rows,chunks_path);atomic_parquet(summaries,docs_path)
            record=dict(configuracao_sha256=state['identity'],arquivo_id=source['arquivo_id'],batch=batch_i,
                documentos=len(summaries),chunks=len(rows),caracteres=sum(d['caracteres'] for d in summaries),
                tokens_documentos=sum(d['tokens_documento'] for d in summaries),tokens_indexados=sum(d['tokens_indexados'] for d in summaries),
                tokens_max=max(d['tokens_max'] for d in summaries),reconstrucao_aprovada=True,
                chunks_arquivo=str(chunks_path.relative_to(state['root'])),chunks_sha256=audit.hash_file(chunks_path),
                documentos_arquivo=str(docs_path.relative_to(state['root'])),documentos_sha256=audit.hash_file(docs_path))
            atomic_json(checkpoint,record);done+=1
            if done==1 or done%10==0:
                current=status(state);elapsed=time.monotonic()-start
                print('Checkpoint:',label,'documentos',current['documentos_processados'],'chunks',current['chunks'],'segundos',round(elapsed,1),flush=True)
            if max_lotes is not None and done>=max_lotes:return state,status(state)
    return state,status(state)


def validate_partition(rows,summaries):
    """Releitura independente: reconstrói por união e confronta o hash do documento-base."""
    bydoc=defaultdict(list)
    for row in rows:bydoc[row['registro_id']].append(row)
    if len({d['registro_id'] for d in summaries})!=len(summaries) or set(bydoc)!={d['registro_id'] for d in summaries}:
        raise ValueError('Documentos ausentes ou repetidos no lote.')
    for doc in summaries:
        chunks=sorted(bydoc[doc['registro_id']],key=lambda r:r['ordem']);cursor=0;digest=hashlib.sha256();previous=None
        if len(chunks)!=doc['chunks']:raise ValueError('Contagem documental de chunks divergente.')
        for i,row in enumerate(chunks):
            a,b=row['inicio'],row['fim'];text=row['texto']
            if row['ordem']!=i or not 0<=a<=cursor<b or len(text)!=b-a:raise ValueError('Offsets ou ordem de chunk inválidos.')
            if not 0<row['tokens']<=500 or row['tokens_com_especiais']!=row['tokens']+2:raise ValueError('Limite de tokens inválido.')
            if base.sha(text)!=row['texto_sha256'] or row['texto_base_sha256']!=doc['texto_base_sha256']:raise ValueError('Hash textual divergente.')
            if previous is not None and a<cursor:
                if a<previous['inicio'] or previous['texto'][a-previous['inicio']:]!=text[:cursor-a]:raise ValueError('Textos divergentes na sobreposição.')
            if row['grupo_avaliacao']!=doc['grupo_avaliacao'] or row['split_proposto']!=doc['split_proposto']:raise ValueError('Partição documental alterada.')
            digest.update(text[cursor-a:].encode('utf-8'));cursor=b;previous=row
        if cursor!=doc['caracteres'] or digest.hexdigest()!=doc['texto_base_sha256']:raise ValueError('Reconstrução por união divergente.')


def finalize(state):
    with writer_lock(state['data']):return _finalize(state)


def _finalize(state):
    progress=status(state)
    if progress['documentos_restantes']:raise ValueError('Corpus ainda parcial; não publicar como concluído.')
    dbpath=state['data']/'auditoria_duplicatas.sqlite'
    conn=sqlite3.connect(dbpath)
    try:
        conn.execute('PRAGMA temp_store=FILE')
        conn.execute('CREATE TABLE IF NOT EXISTS docs(id TEXT PRIMARY KEY,grupo TEXT,split TEXT,tribunal TEXT,arquivo TEXT,chars INTEGER)')
        conn.execute('CREATE TABLE IF NOT EXISTS chunks(id TEXT PRIMARY KEY,text_hash TEXT,doc TEXT,tokens INTEGER)')
        conn.execute('CREATE TABLE IF NOT EXISTS lotes(nome TEXT PRIMARY KEY,hash TEXT)')
        verified=0
        for cp in checkpoints(state):
            name=f"{cp['arquivo_id']}_{cp['batch']:06}"
            chunks=state['root']/cp['chunks_arquivo'];documents=state['root']/cp['documentos_arquivo']
            if audit.hash_file(chunks)!=cp['chunks_sha256'] or audit.hash_file(documents)!=cp['documentos_sha256']:raise ValueError('Parquet de saída alterado.')
            saved=conn.execute('SELECT hash FROM lotes WHERE nome=?',(name,)).fetchone()
            if saved:
                if saved[0]!=cp['chunks_sha256']:raise ValueError('Auditoria de outra versão do lote.')
                continue
            rows=pq.read_table(chunks).to_pylist();docs=pq.read_table(documents).to_pylist()
            validate_partition(rows,docs)
            for doc in docs:
                expected=state['metadata'].get(doc['registro_id'])
                if expected is None or any(doc[k]!=expected[k] for k in ('arquivo_id','tribunal','grupo_avaliacao','split_proposto')):
                    raise ValueError('Documento fora do recorte ou partição da base alterada.')
            with conn:
                conn.executemany('INSERT INTO docs VALUES(?,?,?,?,?,?)',[(d['registro_id'],d['grupo_avaliacao'],d['split_proposto'],d['tribunal'],d['arquivo_id'],d['caracteres']) for d in docs])
                conn.executemany('INSERT INTO chunks VALUES(?,?,?,?)',[(r['chunk_id'],r['texto_sha256'],r['registro_id'],r['tokens']) for r in rows])
                conn.execute('INSERT INTO lotes VALUES(?,?)',(name,cp['chunks_sha256']))
            verified+=1
            if verified%100==0:print('Auditoria de lotes:',verified,flush=True)
        nd=conn.execute('SELECT count(*) FROM docs').fetchone()[0];nc=conn.execute('SELECT count(*) FROM chunks').fetchone()[0]
        if nd!=len(state['metadata']) or nc!=progress['chunks']:raise ValueError('Reconciliação global falhou.')
        leaks=conn.execute('SELECT count(*) FROM (SELECT grupo FROM docs GROUP BY grupo HAVING count(DISTINCT split)>1)').fetchone()[0]
        if leaks:raise ValueError('Grupo documental atravessou partições.')
        duplicate=conn.execute('SELECT count(*),coalesce(sum(n-1),0) FROM (SELECT count(*) n FROM chunks GROUP BY text_hash HAVING count(*)>1)').fetchone()
        hist=[dict(tokens=n,chunks=count) for n,count in conn.execute('SELECT tokens,count(*) FROM chunks GROUP BY tokens ORDER BY tokens')]
        audit.write_csv(state['report']/'distribuicao_tokens.csv',hist)
        audit.write_csv(state['report']/'documentos_por_tribunal.csv',[dict(tribunal=t,documentos=n) for t,n in conn.execute('SELECT tribunal,count(*) FROM docs GROUP BY tribunal ORDER BY count(*) DESC')])
        audit.write_csv(state['report']/'particoes_preservadas.csv',[dict(split=s,documentos=n) for s,n in conn.execute('SELECT split,count(*) FROM docs GROUP BY split')])
        result=dict(progress,status='chunking_validado',ids_documentos_unicos=nd,ids_chunks_unicos=nc,
            reconstrucao_integral_aprovada=True,grupos_atravessando_splits=leaks,
            grupos_chunks_textuais_repetidos=duplicate[0],ocorrencias_textuais_excedentes=duplicate[1],
            repeticoes_preservadas_com_proveniencia=True,unidades_acima_500=0,unidades_acima_512=0,unidades_acima_8192=0)
        atomic_json(state['report']/'concluido.json',result)
        atomic_json(state['report']/'manifesto_lotes.json',dict(configuracao_sha256=state['identity'],lotes=checkpoints(state)))
        return result
    finally:conn.close()
