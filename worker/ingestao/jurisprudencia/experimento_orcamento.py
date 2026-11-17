"""Protocolo de ajuste: ranking completo, contexto centrado, varredura e contrafactuais."""
from pathlib import Path
from itertools import combinations
import json,os,copy
import numpy as np
import pandas as pd
from . import audit,chunking,chunking_suporte as base,chunking_avancado as adv
from . import perguntas_csv,piloto_bge,contexto_centrado as context,cobertura_metricas as cm

ORIGINAL_EIGHT=('juris_001','juris_002','juris_003','juris_004','juris_005','juris_019','juris_020','juris_023')

def encoder_retained(row,view):
    """Apenas corte por limite é truncamento; espaços ignorados pelo tokenizer não o são."""
    if not view['truncado']:return row
    origin=row.get('unidade_indexada_inicio',row['inicio'])
    return dict(row,fim=max(row['inicio'],min(row['fim'],origin+view['fim_retido'])))

def prepare(root):
    root=Path(root).resolve();os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
    source=base.prepare(root);held=piloto_bge.freeze_guard(root,source['queries'])
    queries=[q for q in source['queries'] if q['query_id'] not in held]
    gold=[q for q in source['questions'] if q['query_id'] not in held]
    assert len(queries)==23 and len(gold)>8 and not {q['query_id'] for q in gold}&held
    wanted={ref['registro_id'] for q in gold for g in q['alternativas_suporte'] for ref in g}
    wanted|={d['registro_id'] for d in source['docs'] if d['registro_id'].startswith(('e09c3c5a','1ea70dec'))}
    docs=sorted((d for d in source['docs'] if d['registro_id'] in wanted),key=lambda d:d['registro_id'])
    units={v:[r for d in docs for r in adv.build_chunks(d,v,source['tokenizer'])] for v in adv.TITLES}
    variants={v:dict(index=v,window_tokens=None,section=v=='paragrafo_secao') for v in units}
    variants.update({f'paragrafo_janela_{size}':dict(index='paragrafo',window_tokens=size,section=False) for size in context.WINDOW_SIZES})
    # Auditoria mais ampla é separada da comparação: não acrescenta documentos só a um recuperador.
    all_sections=[r for d in source['docs'] for r in adv.build_chunks(d,'secao_tema',source['tokenizer'])]
    extra=source['tokenizer'].num_special_tokens_to_add(pair=False)
    long_sections=[r for r in all_sections if r['tokens']+extra>8192]
    config=dict(versao=5,seed=adv.SEED,escopo='piloto ampliado com mesmos documentos para BM25 e BGE-M3',
        documentos=[dict(registro_id=d['registro_id'],sha256=base.sha(d['texto']),parent_arquivo=d['parent_arquivo'],parent_sha256=d['parent_sha256']) for d in docs],
        gabarito_sha256=audit.hash_file(root/'avaliacao/dados/jurisprudencia/perguntas_suporte.jsonl'),
        perguntas_com_evidencia=[q['query_id'] for q in gold],consultas_executadas=[q['query_id'] for q in queries],
        perguntas_reservadas=sorted(held),teste_final_executado=False,coorte_original=list(ORIGINAL_EIGHT),
        variantes=variants,orcamentos=list(adv.BUDGETS),ranking='Todas as unidades com score positivo (BM25); todas as unidades (BGE); sem top k fixo na montagem.',
        expansao='Janela simétrica ao redor do parágrafo recuperado, sem usar gabarito; preencher orçamento, deduplicar offsets e cortar pela contagem do texto montado.',
        auditoria_secao_corpus_amplo=dict(documentos=len(source['docs']),unidades=len(all_sections),unidades_longas=len(long_sections),
            corpus_sha256=base.sha(json.dumps([(d['registro_id'],base.sha(d['texto'])) for d in sorted(source['docs'],key=lambda d:d['registro_id'])]))),
        modelo=piloto_bge.MODEL,revisao=piloto_bge.REVISION,dimensao=1024,max_length=8192,
        tokenizador_sha256=base.sha(source['tokenizer'].backend_tokenizer.to_str()),
        codigo_sha256=audit.hash_file(__file__),contexto_codigo_sha256=audit.hash_file(context.__file__),
        chunking_codigo_sha256=audit.hash_file(adv.__file__),base_codigo_sha256=audit.hash_file(base.__file__))
    ident=base.sha(json.dumps(config,sort_keys=True,ensure_ascii=False))
    report=root/'dados/relatorios/jurisprudencia/orcamento_centrado'/ident;data=root/'dados/chunks/jurisprudencia/orcamento_centrado'/ident
    report.mkdir(parents=True,exist_ok=True);data.mkdir(parents=True,exist_ok=True)
    import pyarrow as pa,pyarrow.parquet as pq
    checks=[]
    documents={d['registro_id']:d for d in docs}
    for v,rows in units.items():
        checks.append(dict(versao=v,**adv.unit_audit(rows,documents,source['tokenizer'])))
        pq.write_table(pa.Table.from_pylist(rows),data/(v+'.parquet'),compression='zstd')
    corpus=data/'documentos_base.parquet';pq.write_table(pa.Table.from_pylist([
        dict(registro_id=d['registro_id'],texto=d['texto'],campo_texto=d['texto_principal_campo']) for d in docs]),corpus,compression='zstd')
    pq.write_table(pa.Table.from_pylist(long_sections),data/'secoes_longas_auditoria_ampla.parquet',compression='zstd')
    audit.write_json(report/'configuracao.json',config);audit.write_json(report/'auditoria_unidades.json',checks)
    audit.write_json(report/'manifesto_corpus.json',dict(arquivo=str(corpus.relative_to(root)),sha256=audit.hash_file(corpus)))
    (report/'gabarito_snapshot.jsonl').write_bytes((root/'avaliacao/dados/jurisprudencia/perguntas_suporte.jsonl').read_bytes())
    for module in (__file__,context.__file__,adv.__file__,base.__file__,piloto_bge.__file__):
        (report/('executado_'+Path(module).name)).write_bytes(Path(module).read_bytes())
    print('Protocolo centrado:',len(docs),'documentos;',len(queries),'consultas;',len(gold),'gabaritos;',len(variants),'variantes;',len(long_sections),'seções longas na auditoria ampla',flush=True)
    return dict(root=root,report=report,data=data,docs=documents,questions=queries,gold=gold,units=units,
        variants=variants,tokenizer=source['tokenizer'],long_sections=long_sections,config=config,identity=ident)

def _diagnosis(q,ranking,selected,units,views,variant,version,retriever,budget,used,cuts):
    expected={r['registro_id'] for g in q['alternativas_suporte'] for r in g}
    first=next((r['rank'] for r in ranking if r['registro_id'] in expected),None)
    value=adv.support_fraction(q,selected);doccontext=any(r['registro_id'] in expected for r in selected)
    # O número mínimo e a fragmentação são estruturais; não exigem varrer de novo
    # todos os prefixos do ranking (o primeiro rank de documento já foi registrado).
    structural=cm.evidence_units(q,units)
    retained=[encoder_retained(r,views[r['texto_sha256']]) for r in units if r['registro_id'] in expected]
    enc_loss=max(0.,1-adv.support_fraction(q,retained)) if retriever=='BGE-M3' else None
    reasons=[]
    if value>=1-1e-12:reasons.append('evidência integral no contexto')
    elif not doccontext:reasons.append('documento esperado não chegou ao contexto dentro do orçamento')
    elif value==0:reasons.append('documento correto no contexto, mas trechos sem sobreposição com a evidência')
    else:reasons.append('cobertura parcial dos intervalos esperados')
    if first and first<=5 and value==0:reasons.append('Documento@5 correto não implicou trecho de suporte correto')
    if structural['evidencia_fragmentada']:reasons.append('um intervalo de evidência atravessa fronteira de unidades')
    if cuts:reasons.append('houve corte do contexto por orçamento')
    if enc_loss and enc_loss>1e-12:reasons.append('parte da evidência não estava nos prefixos codificados; fator de risco, não prova causal do ranking')
    return dict(query_id=q['query_id'],versao=version,recuperador=retriever,orcamento=budget,cobertura=value,
        documento_1=first==1,documento_5=first is not None and first<=5,documento_10=first is not None and first<=10,
        primeiro_rank_documento=first,documento_no_contexto=doccontext,trecho_errado=doccontext and value==0,
        evidencia_fragmentada=structural['evidencia_fragmentada'],unidades_minimas=structural['unidades_necessarias_minimas'],
        perda_evidencia_encoder=enc_loss,encoder_executado=retriever=='BGE-M3',
        cortes_contexto=cuts,tokens_utilizados=used,explicacao='; '.join(reasons))

def evaluate(state,vectors,views):
    report=state['report'];packer=context.Packer(state['docs'],state['tokenizer'])
    gold={q['query_id']:q for q in state['gold']};curves=[];details=[];parts=[];ranks=[];cost=[];ablation=[]
    rankings={}
    for index,rows in state['units'].items():
        lexical=base.BM25(rows);matrix=np.stack([vectors[r['texto_sha256']] for r in rows])
        for q in state['questions']:
            rankings[(index,'BM25',q['query_id'])]=lexical.search(q['pergunta'],len(rows))
            scores=matrix@vectors[base.sha(q['pergunta'])]
            order=sorted(range(len(rows)),key=lambda i:(-float(scores[i]),rows[i]['chunk_id']))
            rankings[(index,'BGE-M3',q['query_id'])]=[dict(rows[i],rank=j+1,score=float(scores[i])) for j,i in enumerate(order)]
        print('Ranking completo pronto:',index,flush=True)
    for version,variant in state['variants'].items():
        rows=state['units'][variant['index']]
        for retriever in ('BM25','BGE-M3'):
            for q in state['questions']:
                qid=q['query_id'];ranking=rankings[(variant['index'],retriever,qid)]
                for r in ranking[:10]:ranks.append(dict(query_id=qid,versao=version,recuperador=retriever,**{k:r[k] for k in ('rank','chunk_id','registro_id','inicio','fim','score')}))
                for budget in adv.BUDGETS:
                    selected,used,cuts,examined=packer.pack(ranking,budget,variant['window_tokens'],variant['section'])
                    common=dict(query_id=qid,versao=version,recuperador=retriever,orcamento=budget)
                    support=adv.support_fraction(gold[qid],selected) if qid in gold else None
                    curves.append(dict(common,cobertura=support,tokens_utilizados=used,unidades_distintas=len({r['chunk_id'] for r in selected}),
                        unidades_examinadas=examined,documentos_distintos=len({r['registro_id'] for r in selected}),cortes=cuts,
                        status='avaliada_com_intervalos' if qid in gold else 'busca_executada_sem_intervalo_de_suporte'))
                    if budget==2500:
                        for r in selected:parts.append(dict(common,chunk_id=r['chunk_id'],registro_id=r['registro_id'],rank=r['rank'],inicio=r['inicio'],fim=r['fim']))
                        if qid in gold:
                            details.append(_diagnosis(gold[qid],ranking,selected,rows,views,variant,version,retriever,budget,used,cuts))
                        cost.append(dict(common,tokens=used,unidades=len({r['chunk_id'] for r in selected}),examinadas=examined,
                            tokens_top5_antes=sum(r['tokens'] for r in ranking[:5]),contexto_centrado=variant['section'] or variant['window_tokens'] is not None))
                    if qid in gold and version=='secao_tema' and retriever=='BGE-M3':
                        # Duas perguntas distintas: depende da unidade truncada? depende do conteúdo descartado?
                        clean=[r for r in ranking if not views[r['texto_sha256']]['truncado']]
                        cf,_,_,_=packer.pack(clean,budget)
                        # Sem truncamento, não se perde evidência. Espaços de borda fora dos offsets
                        # do tokenizador não são texto descartado por limite do encoder.
                        encoded=[encoder_retained(r,views[r['texto_sha256']]) for r in selected]
                        ablation.append(dict(common,cobertura=support,cobertura_sem_unidades_truncadas=adv.support_fraction(gold[qid],cf),
                            delta_remocao=support-adv.support_fraction(gold[qid],cf),
                            evidencia_em_unidades_truncadas=adv.support_fraction(gold[qid],[r for r in selected if views[r['texto_sha256']]['truncado']]),
                            evidencia_entregue_fora_prefixo_encoder=max(0.,support-adv.support_fraction(gold[qid],encoded)),
                            unidades_truncadas_recuperadas=len({r['chunk_id'] for r in selected if views[r['texto_sha256']]['truncado']})))
        print('Contextos avaliados:',version,flush=True)
    for name,records in [('cobertura',curves),('diagnostico_por_pergunta',details),('intervalos_contexto_2500',parts),
                         ('ranking_documento_top10',ranks),('custo_real_orcamento',cost),('ablacao_truncamento_secao',ablation)]:
        pd.DataFrame(records).to_csv(report/(name+'.csv'),index=False)
    trunc=[]
    for scope,rows in [('piloto_secao_tema',state['units']['secao_tema']),('auditoria_ampla_secoes_longas',state['long_sections'])]:
        for r in rows:
            view=views[r['texto_sha256']]
            trunc.append(dict(escopo=scope,registro_id=r['registro_id'],chunk_id=r['chunk_id'],inicio=r['inicio'],fim=r['fim'],
                tokens_sem_especiais=r['tokens'],inicio_descartado=r['inicio']+view['fim_retido'] if view['truncado'] else None,**view))
    pd.DataFrame(trunc).to_csv(report/'truncamento_secao_real.csv',index=False)
    frame=pd.DataFrame(curves);valid=frame.dropna(subset=['cobertura'])
    primary=valid[valid.orcamento.eq(2500)].groupby(['recuperador','versao'],as_index=False).agg(
        cobertura_2500=('cobertura','mean'),perguntas=('query_id','size'),tokens_medios=('tokens_utilizados','mean'))
    primary.to_csv(report/'resumo_2500.csv',index=False)
    pairs=[]
    for cohort,subset in [('ajuste_ampliado',valid),('oito_originais',valid[valid.query_id.isin(ORIGINAL_EIGHT)])]:
        pivot=subset[subset.orcamento.eq(2500)].pivot(index='query_id',columns=['recuperador','versao'],values='cobertura')
        for a,b in combinations(pivot.columns,2):
            delta=(pivot[a]-pivot[b]).to_numpy();rng=np.random.default_rng(adv.SEED)
            means=rng.choice(delta,(2000,len(delta)),replace=True).mean(axis=1)
            pairs.append(dict(coorte=cohort,a=' / '.join(a),b=' / '.join(b),n=len(delta),
                vitorias=int((delta>1e-12).sum()),empates=int((abs(delta)<=1e-12).sum()),derrotas=int((delta< -1e-12).sum()),
                delta_media=float(delta.mean()),ic95_inf=float(np.quantile(means,.025)),ic95_sup=float(np.quantile(means,.975)),seed=adv.SEED,replicas=2000))
    pd.DataFrame(pairs).to_csv(report/'bootstrap_pareado.csv',index=False)
    for scope,selection in [('ampliado',valid),('oito_originais',valid[valid.query_id.isin(ORIGINAL_EIGHT)])]:
        selection.groupby(['recuperador','versao','orcamento']).cobertura.mean().reset_index().to_csv(report/('curva_'+scope+'.csv'),index=False)
    audit.write_json(report/'resumo.json',dict(status='concluido',perguntas_buscadas=len(state['questions']),
        perguntas_com_gabarito=len(state['gold']),reservadas=len(state['config']['perguntas_reservadas']),
        corpus_documentos=len(state['docs']),variantes=len(state['variants']),teste_final_executado=False,
        secao_piloto_unidades_truncadas=sum(views[r['texto_sha256']]['truncado'] for r in state['units']['secao_tema']),
        secao_auditoria_ampla_truncadas=len(state['long_sections']),
        nota='A auditoria ampla codifica as seções longas; sua dependência no ranking é avaliada apenas no corpus de recuperação do piloto. Não se extrapola para o corpus integral.'))
    audit.write_json(state['root']/'dados/relatorios/jurisprudencia/orcamento_centrado/ativa.json',dict(
        pasta_relatorios=str(report.relative_to(state['root'])),pasta_dados=str(state['data'].relative_to(state['root'])),identidade=state['identity']))
    return primary

def run(root):
    state=prepare(root);encoder_state=dict(state,units=dict(state['units'],auditoria_ampla=state['long_sections']))
    vectors,views=piloto_bge.encode(encoder_state)
    return evaluate(state,vectors,views)
