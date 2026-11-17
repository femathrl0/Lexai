"""Varredura equilibrada, diagnóstico de falhas e escolha anterior ao teste reservado."""
from pathlib import Path
from itertools import combinations
import json,os,sqlite3
import numpy as np,pandas as pd
from . import audit,chunking,chunking_suporte as base,chunking_avancado as adv
from . import contexto_centrado as context,piloto_bge,perguntas_csv,experimento_orcamento as previous

GRID=((256,0),(500,0),(1000,0),(2500,0),(5000,0),(500,50),(500,100))

def make_fixed(doc,template,tokenizer,size,overlap):
    rows=[];cursor=0
    for i,(a,b) in enumerate(chunking.split_spans(doc['texto'],tokenizer,size,overlap)):
        assert a<=cursor<b and doc['texto'][a:b].strip();cursor=b
        text=doc['texto'][a:b];n=chunking.token_count(text,tokenizer);assert n<=size
        version=f'fixa_{size}_o{overlap}'
        rows.append(dict(template,chunk_id=base.sha('|'.join([version,doc['registro_id'],str(a),str(b)])),
            versao=version,inicio=a,fim=b,texto=text,texto_sha256=base.sha(text),tokens=n,ordem=i,
            contexto_inicio=a,contexto_fim=b,dispositivo_ids=[],metodo_fronteira='tokens_fixos_com_sobreposicao',
            tamanho_alvo=size,sobreposicao_alvo=overlap))
    assert cursor==len(doc['texto'])
    return rows

def prepare(root):
    root=Path(root).resolve();os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
    import pyarrow.parquet as pq,pyarrow as pa
    from transformers import AutoTokenizer
    pointer=json.loads((root/'dados/relatorios/jurisprudencia/orcamento_centrado/ativa.json').read_text(encoding='utf-8'))
    oldreport=root/pointer['pasta_relatorios'];olddata=root/pointer['pasta_dados']
    oldconfig=json.loads((oldreport/'configuracao.json').read_text(encoding='utf-8'))
    docs={d['registro_id']:dict(d,texto_principal_campo=d['campo_texto']) for d in pq.read_table(olddata/'documentos_base.parquet').to_pylist()}
    queries,_=perguntas_csv.load(root);held=piloto_bge.freeze_guard(root,queries)
    queries=[q for q in queries if q['query_id'] not in held];gold=base.load_questions(root);base.validate_questions(gold,docs)
    assert {q['query_id'] for q in gold}==set(oldconfig['perguntas_com_evidencia'])
    assert not {q['query_id'] for q in gold}&held
    tokenizer=AutoTokenizer.from_pretrained(piloto_bge.MODEL,revision=piloto_bge.REVISION,local_files_only=True,use_fast=True)
    original=pq.read_table(olddata/'janela_500.parquet').to_pylist();templates={r['registro_id']:r for r in original}
    units={}
    for size,overlap in GRID:
        key=f'fixa_{size}_o{overlap}'
        units[key]=original if (size,overlap)==(500,0) else [r for d in docs.values() for r in make_fixed(d,templates[d['registro_id']],tokenizer,size,overlap)]
    units['_paragrafo_index']=pq.read_table(olddata/'paragrafo.parquet').to_pylist()
    config=dict(versao=6,grade=[dict(tamanho=s,sobreposicao=o) for s,o in GRID],
        corpus_sha256=audit.hash_file(olddata/'documentos_base.parquet'),corpus_documentos=oldconfig['documentos'],
        origem_relatorios=str(oldreport.relative_to(root)),origem_dados=str(olddata.relative_to(root)),
        origem_manifesto_sha256=audit.hash_file(oldreport/'manifesto_resultados.json'),
        gabarito_sha256=audit.hash_file(root/'avaliacao/dados/jurisprudencia/perguntas_suporte.jsonl'),
        gabarito_anterior_sha256=oldconfig['gabarito_sha256'],query_ids_ajuste=[q['query_id'] for q in queries],
        gabaritos_ajuste=[q['query_id'] for q in gold],reservadas=sorted(held),seed=adv.SEED,orcamentos=list(adv.BUDGETS),
        selecao='Uma configuração de cada família pelo maior Cobertura@2500 com BGE-M3 nas 17 perguntas de ajuste; empate: menos vetores e nome estável.',
        corpus_teste='Mesmo corpus de 18 documentos, sem inserção de documentos guiada pelo gabarito reservado. Fontes de referência externas ao índice permitem diagnosticar ausência de cobertura da base.',
        codigo_sha256=audit.hash_file(__file__),contexto_codigo_sha256=audit.hash_file(context.__file__),
        modelo=piloto_bge.MODEL,revisao=piloto_bge.REVISION,tokenizador_sha256=base.sha(tokenizer.backend_tokenizer.to_str()),
        orcamento_primario=2500,teste_final_executado=False)
    ident=base.sha(json.dumps(config,sort_keys=True,ensure_ascii=False));report=root/'dados/relatorios/jurisprudencia/finalistas'/ident;data=root/'dados/chunks/jurisprudencia/finalistas'/ident
    report.mkdir(parents=True,exist_ok=True);data.mkdir(parents=True,exist_ok=True)
    for v,rows in units.items():pq.write_table(pa.Table.from_pylist(rows),data/(v+'.parquet'),compression='zstd')
    audit.write_json(report/'configuracao.json',config)
    (report/'gabarito_ajuste_snapshot.jsonl').write_bytes((root/'avaliacao/dados/jurisprudencia/perguntas_suporte.jsonl').read_bytes())
    (report/'executado_finalistas_chunking.py').write_bytes(Path(__file__).read_bytes())
    print('Grade escolhida:',len(GRID),'configurações fixas;',len(docs),'documentos;',len(gold),'gabaritos de ajuste',flush=True)
    return dict(root=root,report=report,data=data,docs=docs,questions=queries,gold=gold,units=units,tokenizer=tokenizer,
        oldreport=oldreport,olddata=olddata,config=config,identity=ident)

def diagnose_priorities(state):
    rows=state['units']['fixa_500_o0'];db=sqlite3.connect(state['root']/'dados/chunks/jurisprudencia/cache_bge'/(piloto_bge.REVISION+'_float32_8192.sqlite'))
    def vector(text):
        item=db.execute('SELECT vector FROM embeddings WHERE hash=?',(base.sha(text),)).fetchone();assert item
        return np.frombuffer(item[0],dtype=np.float32)
    matrix=np.stack([vector(r['texto']) for r in rows]);gold={q['query_id']:q for q in state['gold']};out=[]
    packer=context.Packer(state['docs'],state['tokenizer'])
    for qid in ('juris_001','juris_002','juris_023'):
        q=gold[qid];scores=matrix@vector(q['pergunta']);order=sorted(range(len(rows)),key=lambda i:(-float(scores[i]),rows[i]['chunk_id']))
        rank=[dict(rows[i],rank=j+1,score=float(scores[i])) for j,i in enumerate(order)]
        chosen,used,cuts,_=packer.pack(rank,2500);actual=adv.support_fraction(q,chosen)
        evidence=[dict(r,suporte=adv.support_fraction(q,[r])) for r in rank if adv.support_fraction(q,[r])>0]
        oracle=sorted(rank,key=lambda r:(-adv.support_fraction(q,[r]),r['chunk_id']))
        oracle_context,_,_,_=packer.pack(oracle,2500)
        expected={r['registro_id'] for g in q['alternativas_suporte'] for r in g}
        record=dict(query_id=qid,documento_rank=next(r['rank'] for r in rank if r['registro_id'] in expected),
            primeiro_trecho_evidencia_rank=evidence[0]['rank'] if evidence else None,
            cobertura_real_2500=actual,cobertura_oraculo_2500=adv.support_fraction(q,oracle_context),
            oracle_nunca_usado_no_ranking=True,
            unidades_relevantes=[{k:r[k] for k in ('rank','chunk_id','registro_id','inicio','fim','suporte')} for r in evidence],
            top5=[{k:r[k] for k in ('rank','chunk_id','registro_id','inicio','fim','score')} for r in rank[:5]],
            diagnostico='Documento recuperado não garante que as unidades que contêm o fundamento e a decisão estejam no orçamento. O oráculo isola capacidade do chunking de falha de ordenação, sem compor a métrica real.')
        out.append(record)
        print(qid,'doc rank',record['documento_rank'],'evidência rank',record['primeiro_trecho_evidencia_rank'],'real/oráculo',actual,record['cobertura_oraculo_2500'],flush=True)
        for r in rank[:2]:print('TRECHO PARA LEITURA',qid,r['rank'],r['texto'][:650].replace('\n',' '),flush=True)
    db.close();audit.write_json(state['report']/'diagnostico_p01_p02_p23.json',out)
    return out

def paired(frame):
    records=[]
    pivot=frame[frame.orcamento.eq(2500)&frame.cobertura.notna()].pivot(index='query_id',columns=['recuperador','versao'],values='cobertura')
    for a,b in combinations(pivot.columns,2):
        delta=(pivot[a]-pivot[b]).to_numpy();rng=np.random.default_rng(adv.SEED);means=rng.choice(delta,(2000,len(delta)),replace=True).mean(axis=1)
        records.append(dict(a=' / '.join(a),b=' / '.join(b),n=len(delta),vitorias=int((delta>1e-12).sum()),
            empates=int((abs(delta)<=1e-12).sum()),derrotas=int((delta< -1e-12).sum()),delta_media=float(delta.mean()),
            ic95_inf=float(np.quantile(means,.025)),ic95_sup=float(np.quantile(means,.975)),seed=adv.SEED,replicas=2000))
    return pd.DataFrame(records)

def evaluate(state,vectors,views):
    curves=[];diagnostics=[];gold={q['query_id']:q for q in state['gold']};packer=context.Packer(state['docs'],state['tokenizer'])
    rankings={}
    for index,rows in state['units'].items():
        lexical=base.BM25(rows);matrix=np.stack([vectors[r['texto_sha256']] for r in rows])
        for retriever in ('BM25','BGE-M3'):
            for q in state['questions']:
                if retriever=='BM25':rank=lexical.search(q['pergunta'],len(rows))
                else:
                    scores=matrix@vectors[base.sha(q['pergunta'])];order=sorted(range(len(rows)),key=lambda i:(-float(scores[i]),rows[i]['chunk_id']))
                    rank=[dict(rows[i],rank=j+1,score=float(scores[i])) for j,i in enumerate(order)]
                rankings[(index,retriever,q['query_id'])]=rank
    plans={f'fixa_{s}_o{o}':(f'fixa_{s}_o{o}',None) for s,o in GRID}
    plans.update({f'paragrafo_janela_{size}':('_paragrafo_index',size) for size in context.WINDOW_SIZES})
    for version,(index,cap) in plans.items():
        for retriever in ('BM25','BGE-M3'):
            for q in state['questions']:
                rank=rankings[(index,retriever,q['query_id'])]
                for budget in adv.BUDGETS:
                    selected,used,cuts,examined=packer.pack(rank,budget,window_tokens=cap)
                    curves.append(dict(query_id=q['query_id'],recuperador=retriever,versao=version,orcamento=budget,
                        cobertura=adv.support_fraction(gold[q['query_id']],selected) if q['query_id'] in gold else None,
                        tokens_utilizados=used,unidades_distintas=len({r['chunk_id'] for r in selected}),cortes=cuts,examinadas=examined))
                    if budget==2500 and q['query_id'] in ('juris_001','juris_002','juris_023'):
                        g=gold[q['query_id']];expected={r['registro_id'] for group in g['alternativas_suporte'] for r in group}
                        diagnostics.append(dict(query_id=q['query_id'],recuperador=retriever,versao=version,
                            primeiro_rank_documento=next((r['rank'] for r in rank if r['registro_id'] in expected),None),
                            primeiro_rank_evidencia=next((r['rank'] for r in rank if adv.support_fraction(g,[r])>0),None),
                            documento_no_contexto=any(r['registro_id'] in expected for r in selected),
                            cobertura_2500=adv.support_fraction(g,selected),cortes_contexto=cuts,
                            limite_encoder_real=8192,encoder_truncou_alguma_unidade=any(views[r['texto_sha256']]['truncado'] for r in state['units'][index])))
        print('Varredura avaliada:',version,flush=True)
    combined=pd.DataFrame(curves);combined.to_csv(state['report']/'cobertura_ajuste.csv',index=False)
    pd.DataFrame(diagnostics).to_csv(state['report']/'diagnostico_tres_perguntas_por_grade.csv',index=False)
    summary=combined[combined.orcamento.eq(2500)&combined.cobertura.notna()].groupby(['recuperador','versao'],as_index=False).agg(
        cobertura_2500=('cobertura','mean'),perguntas=('query_id','size'),tokens_medios=('tokens_utilizados','mean'))
    counts={v:len(rows) for v,rows in state['units'].items()}
    import pyarrow.parquet as pq
    para_count=pq.ParquetFile(state['olddata']/'paragrafo.parquet').metadata.num_rows
    summary['vetores_indice']=summary.versao.map(lambda v:counts.get(v,para_count))
    summary.to_csv(state['report']/'resumo_2500.csv',index=False);pairs=paired(combined);pairs.to_csv(state['report']/'bootstrap_ajuste.csv',index=False)
    selected=[]
    for family,prefix in [('fixa','fixa_'),('paragrafo_janela','paragrafo_janela_')]:
        candidates=summary[(summary.recuperador=='BGE-M3')&summary.versao.str.startswith(prefix)]
        winner=candidates.sort_values(['cobertura_2500','vetores_indice','versao'],ascending=[False,True,True]).iloc[0].to_dict()
        selected.append(dict(familia=family,**winner))
    audit.write_json(state['report']/'finalistas_selecionadas.json',selected)
    audit.write_json(state['report']/'resumo.json',dict(status='ajuste_concluido',configuracoes_fixas=7,configuracoes_paragrafo=7,
        consultas_ajuste=23,gabaritos_ajuste=17,reservadas=7,teste_final_executado=False,finalistas=selected))
    audit.write_json(state['root']/'dados/relatorios/jurisprudencia/finalistas/ativa.json',dict(pasta_relatorios=str(state['report'].relative_to(state['root'])),
        pasta_dados=str(state['data'].relative_to(state['root'])),identidade=state['identity']))
    return summary

def run(root):
    state=prepare(root);diagnose_priorities(state);vectors,views=piloto_bge.encode(state)
    return evaluate(state,vectors,views)
