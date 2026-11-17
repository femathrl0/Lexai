"""Piloto pareado BM25/BGE-M3, com cache local e corpus idêntico e versionado."""
from pathlib import Path
import os, json, sqlite3, time
import numpy as np
import pandas as pd
from . import audit, chunking, chunking_suporte as base, chunking_avancado as adv
from . import cobertura_metricas as cm

MODEL='BAAI/bge-m3'
REVISION='5617a9f61b028005a4858fdac845db406aefb181'

def encoder_view(text,tokenizer,limit=8192):
    full=tokenizer(text,add_special_tokens=True,truncation=False,verbose=False)['input_ids']
    kept=tokenizer(text,add_special_tokens=True,truncation=True,max_length=limit,
                   return_offsets_mapping=True,verbose=False)
    stop=max((b for a,b in kept['offset_mapping']),default=0)
    return dict(tokens_com_especiais=len(full),tokens_encoder=len(kept['input_ids']),
                fim_retido=stop,truncado=len(full)>limit)

def expanded_cost(ranking,documents,tokenizer):
    """Custo do top-5 entregue após expansão, união de intervalos e separadores."""
    selected,used,_=adv.context_at_budget(ranking[:5],documents,tokenizer,10**9)
    return dict(tokens_indice_top5=sum(r['tokens'] for r in ranking[:5]),
                tokens_contexto_top5_expandido=used,segmentos_expandidos=len(selected))

def freeze_guard(root,queries):
    frozen=json.loads((root/'avaliacao/dados/jurisprudencia/reserva_piloto_congelada.json').read_text(encoding='utf-8'))
    byid={q['query_id']:q for q in queries}
    for ident,digest in frozen['conteudo_reservado_sha256'].items():
        assert base.sha(json.dumps(byid[ident],sort_keys=True,ensure_ascii=False))==digest
    return set(frozen['perguntas_reservadas'])

def prepare(root):
    root=Path(root).resolve();os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
    state=base.prepare(root); held=freeze_guard(root,state['queries'])
    golden=[q for q in state['questions'] if q['query_id'] not in held]
    assert len(golden)==8 and not any(q['query_id'] in held for q in golden)
    expected={r['registro_id'] for q in golden for g in q['alternativas_suporte'] for r in g}
    # Distratores escolhidos por dificuldade documental: mérito alegado vs recurso inadmissível,
    # e prescrição de execução coletiva vs condenação individual. Não se escolhem pelo score denso.
    prefixes=('e09c3c5a','1ea70dec')
    extra={next(d['registro_id'] for d in state['docs'] if d['registro_id'].startswith(p)) for p in prefixes}
    docs=sorted((d for d in state['docs'] if d['registro_id'] in expected|extra),key=lambda d:d['registro_id'])
    config=dict(versao=1,escopo='piloto_curado_com_distratores; não representa o corpus integral',
        seed=adv.SEED,documentos=[dict(registro_id=d['registro_id'],sha256=base.sha(d['texto']),
             parent_arquivo=d['parent_arquivo'],parent_sha256=d['parent_sha256'],papel='suporte' if d['registro_id'] in expected else 'distrator') for d in docs],
        gabarito_sha256=audit.hash_file(root/'avaliacao/dados/jurisprudencia/perguntas_suporte.jsonl'),
        perguntas_avaliadas=[q['query_id'] for q in golden],perguntas_reservadas=sorted(held),
        modelo=MODEL,revisao=REVISION,encoder_max_length=8192,dimensao=1024,
        pooling='SentenceTransformer do snapshot local; embeddings densos normalizados',
        cpu_threads=4,ranking_profundidade=50,orcamentos=list(adv.BUDGETS),
        codigo_sha256=audit.hash_file(__file__),codigo_chunking_sha256=audit.hash_file(adv.__file__),
        tokenizador_sha256=base.sha(state['tokenizer'].backend_tokenizer.to_str()),
        corpus_identico_por_recuperador=True,teste_final_executado=False)
    ident=base.sha(json.dumps(config,sort_keys=True,ensure_ascii=False))
    report=root/'dados/relatorios/jurisprudencia/piloto_bge'/ident;report.mkdir(parents=True,exist_ok=True)
    data=root/'dados/chunks/jurisprudencia/piloto_bge'/ident;data.mkdir(parents=True,exist_ok=True)
    audit.write_json(report/'configuracao.json',config)
    for module in (__file__,adv.__file__,base.__file__):
        (report/('executado_'+Path(module).name)).write_bytes(Path(module).read_bytes())
    import pyarrow as pa, pyarrow.parquet as pq
    corpus=data/'documentos_base.parquet'
    pq.write_table(pa.Table.from_pylist([dict(registro_id=d['registro_id'],texto=d['texto'],
                       campo_texto=d['texto_principal_campo']) for d in docs]),corpus,compression='zstd')
    audit.write_json(report/'manifesto_corpus.json',dict(arquivo=str(corpus.relative_to(root)),sha256=audit.hash_file(corpus)))
    units={};checks=[]
    documents={d['registro_id']:d for d in docs}
    for version in adv.TITLES:
        rows=[r for d in docs for r in adv.build_chunks(d,version,state['tokenizer'])]
        check=adv.unit_audit(rows,documents,state['tokenizer']);check['versao']=version;checks.append(check)
        pq.write_table(pa.Table.from_pylist(rows),data/(version+'.parquet'),compression='zstd');units[version]=rows
    audit.write_json(report/'auditoria_chunking.json',checks)
    print('Piloto:',len(docs),'acórdãos;',len(golden),'perguntas; reserva:',len(held),flush=True)
    return dict(root=root,report=report,data=data,docs=documents,questions=golden,units=units,
                tokenizer=state['tokenizer'],config=config,identity=ident)

def encode(state):
    """Uma entrada de cache por texto e snapshot: persiste após cada lote."""
    import torch
    from sentence_transformers import SentenceTransformer
    torch.set_num_threads(4)
    model=SentenceTransformer(MODEL,revision=REVISION,local_files_only=True,device='cpu')
    model.max_seq_length=8192
    assert model.tokenizer.truncation_side=='right' and model.get_embedding_dimension()==1024
    assert base.sha(model.tokenizer.backend_tokenizer.to_str())==state['config']['tokenizador_sha256']
    cache=state['root']/'dados/chunks/jurisprudencia/cache_bge';cache.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(cache/(REVISION+'_float32_8192.sqlite'))
    db.execute('CREATE TABLE IF NOT EXISTS embeddings (hash TEXT PRIMARY KEY, vector BLOB NOT NULL, view TEXT NOT NULL)')
    texts={base.sha(r['texto']):r['texto'] for rows in state['units'].values() for r in rows}
    for q in state['questions']:texts[base.sha(q['pergunta'])]=q['pergunta']
    views={key:encoder_view(t,state['tokenizer']) for key,t in texts.items()}
    missing=[key for key in texts if db.execute('SELECT 1 FROM embeddings WHERE hash=?',(key,)).fetchone() is None]
    missing.sort(key=lambda key:(views[key]['tokens_encoder'],key))
    print('Entradas únicas:',len(texts),'cache:',len(texts)-len(missing),
          'tokens a codificar:',sum(views[k]['tokens_encoder'] for k in missing),flush=True)
    start=time.monotonic();done=0
    while missing:
        batch=[missing.pop(0)];cost=views[batch[0]]['tokens_encoder']
        while missing and len(batch)<8 and (len(batch)+1)*views[missing[0]]['tokens_encoder']<=4096:
            batch.append(missing.pop(0))
        vectors=model.encode([texts[k] for k in batch],batch_size=len(batch),normalize_embeddings=True,
                             convert_to_numpy=True,show_progress_bar=False)
        assert vectors.shape==(len(batch),1024) and np.isfinite(vectors).all()
        assert np.allclose(np.linalg.norm(vectors,axis=1),1,atol=1e-5)
        for key,vector in zip(batch,vectors):
            db.execute('INSERT INTO embeddings VALUES(?,?,?)',(key,np.asarray(vector,dtype=np.float32).tobytes(),json.dumps(views[key])))
        db.commit();done+=len(batch)
        status=dict(entradas_unicas=len(texts),entradas_pendentes=len(missing),geradas_nesta_execucao=done,
                    segundos=time.monotonic()-start,ultimo_lote_tokens_max=views[batch[-1]]['tokens_encoder'])
        audit.write_json(state['report']/'progresso_encoder.json',status)
        if done%40<len(batch) or not missing:print('BGE checkpoint:',status,flush=True)
    vectors={};cached_views={}
    for key in texts:
        vector,view=db.execute('SELECT vector,view FROM embeddings WHERE hash=?',(key,)).fetchone()
        vectors[key]=np.frombuffer(vector,dtype=np.float32).copy();cached_views[key]=json.loads(view)
        assert cached_views[key]==views[key]
    db.close()
    audit.write_json(state['report']/'execucao_encoder.json',dict(modelo=MODEL,revisao=REVISION,limite=8192,
        entradas_unicas=len(texts),vetores_gerados_nesta_execucao=done,cache_reutilizado=len(texts)-done,
        segundos=time.monotonic()-start,consultas_codificadas=[q['query_id'] for q in state['questions']],
        reserva_codificada=False,device='cpu',dtype='float32',dimensao=1024))
    return vectors,views

def evaluate(state,vectors,views):
    curves=[];costs=[];evidence=[];rankings=[];trunc=[];diagnostics=[]
    for version,rows in state['units'].items():
        bm25=base.BM25(rows);matrix=np.stack([vectors[r['texto_sha256']] for r in rows])
        retained=[dict(r,fim=r['inicio']+views[r['texto_sha256']]['fim_retido']) for r in rows]
        for r in rows:
            v=views[r['texto_sha256']]
            trunc.append(dict(versao=version,chunk_id=r['chunk_id'],registro_id=r['registro_id'],inicio=r['inicio'],fim=r['fim'],
                inicio_descartado=r['inicio']+v['fim_retido'] if v['truncado'] else None,**v))
        for retriever in ('BM25','BGE-M3'):
            for q in state['questions']:
                if retriever=='BM25':ranking=bm25.search(q['pergunta'],50)
                else:
                    scores=matrix@vectors[base.sha(q['pergunta'])]
                    order=sorted(range(len(rows)),key=lambda i:(-float(scores[i]),rows[i]['chunk_id']))[:50]
                    ranking=[dict(rows[i],rank=j+1,score=float(scores[i])) for j,i in enumerate(order)]
                common=dict(versao=version,recuperador=retriever,query_id=q['query_id'])
                costs.append(dict(common,**expanded_cost(ranking,state['docs'],state['tokenizer'])))
                ev=cm.evidence_units(q,rows,ranking)
                loss=max(0.,adv.support_fraction(q,rows)-adv.support_fraction(q,retained))
                evidence.append(dict(common,**ev,fracao_evidencia_perdida_encoder=loss if retriever=='BGE-M3' else None,
                    evidencia_truncada_encoder=loss>1e-12 if retriever=='BGE-M3' else None,
                    encoder_executado=retriever=='BGE-M3'))
                for r in ranking:
                    rankings.append(dict(common,**{k:r[k] for k in ('chunk_id','registro_id','rank','score','inicio','fim','tokens','secao','tema')}))
                diag=adv.diagnose(q,ranking[:5],rows,state['tokenizer'])
                diag['truncamento_encoder_real']=loss>1e-12 if retriever=='BGE-M3' else None
                diag['fracao_evidencia_perdida_encoder_real']=loss if retriever=='BGE-M3' else None
                diag['base_diagnostico']='top 5 antes da expansão; orçamento avaliado separadamente na curva'
                diagnostics.append(dict(common,**diag))
                for budget in adv.BUDGETS:
                    selected,used,cuts=adv.context_at_budget(ranking,state['docs'],state['tokenizer'],budget)
                    curves.append(dict(common,orcamento=budget,cobertura=adv.support_fraction(q,selected),
                        tokens_utilizados=used,cortes_orcamento=cuts,documentos=len({r['registro_id'] for r in selected})))
    report=state['report']
    for name,records in [('cobertura_por_pergunta',curves),('custo_apos_expansao',costs),('evidencia',evidence),
                         ('truncamento_real_encoder',trunc),('ranking',rankings),('diagnostico_falhas',diagnostics)]:
        pd.DataFrame(records).to_csv(report/(name+'.csv'),index=False,encoding='utf-8')
    frame=pd.DataFrame(curves);primary=frame[frame.orcamento.eq(2500)].groupby(['recuperador','versao'],as_index=False).agg(
        cobertura_media_2500=('cobertura','mean'),perguntas=('query_id','size'),tokens_medios=('tokens_utilizados','mean'))
    primary.to_csv(report/'resumo_2500.csv',index=False)
    summary=pd.DataFrame(costs).groupby(['recuperador','versao']).agg(
        mediana=('tokens_contexto_top5_expandido','median'),p90=('tokens_contexto_top5_expandido',lambda s:s.quantile(.9)),
        maximo=('tokens_contexto_top5_expandido','max')).reset_index()
    summary.to_csv(report/'custo_expandido_resumo.csv',index=False)
    checks=json.loads((report/'auditoria_chunking.json').read_text(encoding='utf-8'))
    for check in checks:
        check['vetores_indexados_bge']=len(state['units'][check['versao']])
        check['textos_vetorizados_unicos_bge']=len({r['texto_sha256'] for r in state['units'][check['versao']]})
        check['vetores_gerados']=check['textos_vetorizados_unicos_bge']
        check['motivo_vetores_gerados']='BGE-M3 executado; textos idênticos reutilizam o mesmo vetor, inclusive entre estratégias. BM25 não usa vetores.'
    audit.write_json(report/'auditoria_chunking.json',checks)
    pd.DataFrame(checks).drop(columns=['metodos_fronteira']).to_csv(report/'auditoria_chunking.csv',index=False)
    # Identifica perguntas outliers pela regra de Tukey em escala log, sem ocultar os extremos.
    c=pd.DataFrame(costs);out=[]
    for key,g in c.groupby(['recuperador','versao']):
        logged=np.log1p(g.tokens_contexto_top5_expandido);q1,q3=logged.quantile([.25,.75]);mask=(logged<q1-1.5*(q3-q1))|(logged>q3+1.5*(q3-q1))
        out.extend(g[mask].to_dict('records'))
    pd.DataFrame(out,columns=c.columns).to_csv(report/'outliers_contexto_expandido.csv',index=False)
    paired=[];rng=np.random.default_rng(adv.SEED)
    # Mesma pergunta e mesmo corpus, tanto entre estratégias como entre recuperadores.
    from itertools import combinations
    values=frame[frame.orcamento.eq(2500)].pivot(index='query_id',columns=['recuperador','versao'],values='cobertura')
    for a,b in combinations(values.columns,2):
        delta=(values[a]-values[b]).to_numpy();means=rng.choice(delta,(2000,len(delta)),replace=True).mean(axis=1)
        paired.append(dict(a=' / '.join(a),b=' / '.join(b),n=len(delta),vitorias=int((delta>1e-12).sum()),
            empates=int((abs(delta)<=1e-12).sum()),derrotas=int((delta< -1e-12).sum()),delta_media=float(delta.mean()),
            ic95_inf=float(np.quantile(means,.025)),ic95_sup=float(np.quantile(means,.975)),seed=adv.SEED,replicas=2000))
    pd.DataFrame(paired).to_csv(report/'estatistica_pareada.csv',index=False)
    audit.write_json(report/'resumo.json',dict(estado='concluido',escopo=state['config']['escopo'],
        acórdãos=len(state['docs']),perguntas_com_gabarito=len(state['questions']),perguntas_reservadas=7,
        teste_final_executado=False,metrica='Cobertura@2500',resultados=primary.to_dict('records'),
        conclusao='Comparação exploratória em piloto enriquecido com documentos de suporte; não estima desempenho no corpus integral nem qualidade de resposta de LLM.'))
    plot(state)
    audit.write_json(state['root']/'dados/relatorios/jurisprudencia/piloto_bge/ativa.json',dict(pasta_relatorios=str(report.relative_to(state['root'])),
        pasta_dados=str(state['data'].relative_to(state['root'])),identidade=state['identity']))
    return primary

def plot(state):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    report=state['report'];frame=pd.read_csv(report/'cobertura_por_pergunta.csv')
    fig,axes=plt.subplots(1,2,figsize=(14,5),sharey=True)
    for ax,retriever in zip(axes,('BM25','BGE-M3')):
        for version,g in frame[frame.recuperador.eq(retriever)].groupby('versao',sort=False):
            avg=g.groupby('orcamento').cobertura.mean();ax.plot(avg.index,avg.values,marker='o',label=version)
        ax.set(title=retriever+' — piloto, 8 perguntas',xlabel='Orçamento de contexto (tokens)',ylim=(0,1.02),xticks=list(adv.BUDGETS));ax.grid(alpha=.2)
    axes[0].set_ylabel('Cobertura média da evidência');axes[1].legend(fontsize=8)
    fig.tight_layout();fig.savefig(report/'curva_cobertura.png',dpi=150);plt.close(fig)
    costs=pd.read_csv(report/'custo_apos_expansao.csv');fig,axes=plt.subplots(1,2,figsize=(16,6),sharey=True)
    for ax,retriever in zip(axes,('BM25','BGE-M3')):
        groups=[costs[(costs.recuperador==retriever)&(costs.versao==v)] for v in adv.TITLES]
        ax.boxplot([g.tokens_contexto_top5_expandido for g in groups],tick_labels=list(adv.TITLES),showfliers=False)
        for i,g in enumerate(groups,1):
            ax.scatter(np.full(len(g),i),g.tokens_contexto_top5_expandido,s=15,alpha=.65)
            for r in g.itertuples():ax.annotate(r.query_id.replace('juris_','P'),(i,r.tokens_contexto_top5_expandido),fontsize=6,xytext=(3,0),textcoords='offset points')
        ax.set_yscale('log');ax.set_title(retriever+' — top 5 após expansão');ax.tick_params(axis='x',rotation=45);ax.grid(axis='y',alpha=.2)
    axes[0].set_ylabel('Tokens de contexto após expansão e deduplicação (log)');fig.tight_layout();fig.savefig(report/'custo_expandido_log.png',dpi=150);plt.close(fig)

def run(root):
    state=prepare(root);vectors,views=encode(state);return evaluate(state,vectors,views)
