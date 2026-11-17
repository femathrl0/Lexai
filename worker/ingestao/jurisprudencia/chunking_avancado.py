"""Avaliação por intervalos, orçamento de contexto e protocolo pareado sem LLM."""
from pathlib import Path
from itertools import combinations
from collections import Counter,defaultdict
import copy
import hashlib
import json
import math
import re

import numpy as np
import pandas as pd

from . import audit,chunking,chunking_suporte as base,cobertura_metricas

SEED=20261114
BUDGETS=(500,1000,2500,5000)
TITLES=dict(base.VERSOES,paragrafo_minimo='Parágrafo — mínimo de 128 tokens',
            secao_teto='Seção/tema — teto de 500 tokens',paragrafo_secao='Parágrafo com expansão para seção')
PARAMS=dict(seed=SEED,orcamentos=list(BUDGETS),profundidade_busca=50,minimo_paragrafo_tokens=128,
            metrica_principal='Cobertura@T',resumo_principal_T=2500,
            teto_secao_tokens=500,bootstrap_replicas=2000,fracao_teste_alvo=.2,
            politica_contexto='ranking; núcleo do trecho primeiro; expansão depois; deduplicação de intervalos; prefixo explícito quando o orçamento acaba',
            encoder_executado=False,limites_encoder_simulados=[512,8192])


def original_reference(document,start,end,section=None):
    """Intervalo no documento-base inteiro anterior ao chunking, nunca coordenadas locais do chunk."""
    if not 0<=start<end<=len(document['texto']):raise ValueError('Intervalo de gabarito inválido.')
    ref=dict(registro_id=document['registro_id'],campo_texto=document['texto_principal_campo'],inicio=start,fim=end,
             texto_sha256=base.sha(document['texto'][start:end]),texto_base_sha256=base.sha(document['texto']),
             espaco_offsets='documento_base_protegido')
    if section:ref['secao_esperada']=section
    return ref


def merge_ranges(ranges):
    merged=[]
    for a,b in sorted(ranges):
        if b<=a:continue
        if merged and a<=merged[-1][1]:merged[-1]=(merged[-1][0],max(b,merged[-1][1]))
        else:merged.append((a,b))
    return merged


def ref_fraction(ref,results):
    ranges=[(max(ref['inicio'],r['inicio']),min(ref['fim'],r['fim'])) for r in results
            if r['registro_id']==ref['registro_id'] and r['campo_texto']==ref['campo_texto']]
    return sum(b-a for a,b in merge_ranges(ranges))/(ref['fim']-ref['inicio'])


def support_fraction(question,results):
    """União sem contar sobreposições duas vezes; melhor alternativa completa, ponderada por caracteres."""
    values=[]
    for group in question['alternativas_suporte']:
        refs=defaultdict(list)
        for ref in group:refs[(ref['registro_id'],ref['campo_texto'])].append((ref['inicio'],ref['fim']))
        numerator=denominator=0
        for (ident,field),ranges in refs.items():
            for a,b in merge_ranges(ranges):
                ref=dict(registro_id=ident,campo_texto=field,inicio=a,fim=b)
                denominator+=b-a;numerator+=(b-a)*ref_fraction(ref,results)
        values.append(numerator/denominator)
    return max(values) if values else None


def sections(text):
    matches=list(base.SECOES.finditer(text))
    cuts=sorted({0,len(text)}|{m.start() for m in matches})
    return [(a,b) for a,b in zip(cuts,cuts[1:]) if text[a:b].strip()]


def build_chunks(doc,version,tokenizer):
    section_ranges=sections(doc['texto'])
    if version in base.VERSOES:
        rows=base.make_chunks(doc,version,tokenizer)
    else:
        source='secao_tema' if version=='secao_teto' else 'paragrafo'
        rows=copy.deepcopy(base.make_chunks(doc,source,tokenizer))
        text=doc['texto'];section_ranges=sections(text)
        if version=='paragrafo_minimo':
            aligned=[]
            for row in rows:
                cuts=sorted({row['inicio'],row['fim']}|{a for a,b in section_ranges if row['inicio']<a<row['fim']})
                for a,b in zip(cuts,cuts[1:]):
                    item=dict(row,inicio=a,fim=b,texto=text[a:b])
                    item['tokens']=chunking.token_count(item['texto'],tokenizer)
                    aligned.append(item)
            rows=aligned
            merged=[]
            # Títulos delimitam seções: agrupamento mínimo nunca junta relatório e fundamentação.
            for row in rows:
                row['secao_grupo']=next((a for a,b in section_ranges if a<=row['inicio']<b),0)
                if merged and merged[-1]['secao_grupo']==row['secao_grupo'] and merged[-1]['tokens']<128:
                    merged[-1]['fim']=row['fim'];merged[-1]['texto']=text[merged[-1]['inicio']:row['fim']]
                    merged[-1]['tokens']=chunking.token_count(merged[-1]['texto'],tokenizer)
                else:merged.append(row)
            rows=merged
        elif version=='secao_teto':
            capped=[]
            for row in rows:
                preferred=chunking.boundaries(row['texto'])
                for a,b in chunking.split_spans(row['texto'],tokenizer,500,0,preferred):
                    r=dict(row,inicio=row['inicio']+a,fim=row['inicio']+b,texto=row['texto'][a:b])
                    r['tokens']=chunking.token_count(r['texto'],tokenizer);r['dispositivo_ids']=[]
                    capped.append(r)
            rows=capped
        elif version!='paragrafo_secao':raise ValueError('Variante desconhecida.')
    methods={'janela_500':'limite_fixo_tokens','paragrafo':'formatacao_paragrafo',
             'secao_tema':'titulo_secao_e_transicao_tema','paragrafo_minimo':'agrupar_paragrafos_na_mesma_secao',
             'secao_teto':'secao_tema_com_limite_tokens_e_preferencia_paragrafos','paragrafo_secao':'formatacao_paragrafo_com_contexto_secao'}
    for index,row in enumerate(rows):
        row['versao']=version;row['ordem']=index
        row['chunk_id']=base.sha('|'.join([version,doc['registro_id'],str(row['inicio']),str(row['fim'])]))
        row['texto_sha256']=base.sha(row['texto'])
        row['metodo_fronteira']=methods[version]+':'+row['metodo_paragrafo']
        row['contexto_inicio']=row['inicio'];row['contexto_fim']=row['fim']
        if version=='paragrafo_secao':
            # Um parágrafo que atravessa um título irregular não é encurtado na expansão.
            intersections=[(a,b) for a,b in section_ranges if a<row['fim'] and row['inicio']<b]
            if intersections:
                row['contexto_inicio']=min(a for a,b in intersections)
                row['contexto_fim']=max(b for a,b in intersections)
    if version=='secao_teto':
        for row in rows:
            if row['secao'] in ('fundamentacao','voto') and row['tema'] not in ('multiplos_temas','nao_identificado'):
                matches=[r['chunk_id'] for r in rows if r['secao']=='dispositivo' and r['tema']==row['tema']]
                if len(matches)==1:row['dispositivo_ids']=matches
    return rows


def unit_audit(rows,documents,tokenizer):
    by_doc=defaultdict(list)
    for row in rows:by_doc[row['registro_id']].append(row)
    if set(by_doc)!=set(documents):raise ValueError('Documentos faltando na reconstrução.')
    for ident,parts in by_doc.items():
        ordered=sorted(parts,key=lambda r:r['inicio']);cursor=0
        for row in ordered:
            if row['inicio']!=cursor or documents[ident]['texto'][row['inicio']:row['fim']]!=row['texto']:
                raise ValueError('Reconstrução sem perdas falhou.')
            if not row['metodo_fronteira']:raise ValueError('Método de fronteira ausente.')
            cursor=row['fim']
        if cursor!=len(documents[ident]['texto']) or ''.join(r['texto'] for r in ordered)!=documents[ident]['texto']:
            raise ValueError('Texto-base não reconstruído.')
    structural=[r for r in rows if r['secao']!='nao_classificada']
    def fraction(key,predicate):return sum(predicate(r[key]) for r in structural)/len(structural) if structural else None
    extra=tokenizer.num_special_tokens_to_add(pair=False) if hasattr(tokenizer,'num_special_tokens_to_add') else 0
    return dict(unidades=len(rows),acima_512=sum(r['tokens']>512 for r in rows),acima_8192=sum(r['tokens']>8192 for r in rows),
                risco_encoder_512_com_especiais=sum(r['tokens']+extra>512 for r in rows),
                risco_encoder_8192_com_especiais=sum(r['tokens']+extra>8192 for r in rows),
                fracao_secao_ambigua=fraction('secao',lambda x:x=='ambigua'),
                fracao_secao_nao_identificada=fraction('secao',lambda x:x=='nao_identificada'),
                fracao_tema_ambiguo=fraction('tema',lambda x:x=='multiplos_temas'),
                fracao_tema_nao_identificado=fraction('tema',lambda x:x=='nao_identificado'),
                metodos_fronteira=dict(Counter(r['metodo_fronteira'] for r in rows)),
                reconstrucao_texto_base='aprovada',vetores_planejados=len(rows),vetores_gerados=0,
                motivo_vetores_gerados='Recuperador BM25: nenhum encoder foi executado.')


def uncovered(a,b,seen):
    parts=[(a,b)]
    for x,y in merge_ranges(seen):
        parts=[piece for u,v in parts for piece in ((u,min(x,v)),(max(y,u),v)) if piece[0]<piece[1]]
    return parts


def context_at_budget(ranking,documents,tokenizer,budget):
    """Empacota texto realmente contado, sem duplicar offsets, e identifica cortes explícitos."""
    if budget<=0:raise ValueError('Orçamento inválido.')
    selected=[];texts=[];seen=defaultdict(list);cuts=0
    for row in ranking:
        ident=row['registro_id'];text=documents[ident]['texto']
        candidates=[(row['inicio'],row['fim'])]
        if row.get('contexto_inicio',row['inicio'])<row['inicio']:candidates.append((row['contexto_inicio'],row['inicio']))
        if row.get('contexto_fim',row['fim'])>row['fim']:candidates.append((row['fim'],row['contexto_fim']))
        for a,b in candidates:
            for start,end in uncovered(a,b,seen[ident]):
                content=text[start:end]
                if not content.strip():continue
                trial='\n\n'.join(texts+[content])
                if chunking.token_count(trial,tokenizer)>budget:
                    # Busca o maior prefixo de tokens que cabe; não é truncamento por encoder.
                    positions=chunking.offsets(content,tokenizer)
                    lo=0;hi=len(positions)
                    while lo<hi:
                        mid=(lo+hi+1)//2
                        stop=positions[mid-1][1]
                        if chunking.token_count('\n\n'.join(texts+[content[:stop]]),tokenizer)<=budget:lo=mid
                        else:hi=mid-1
                    if not lo:return selected,chunking.token_count('\n\n'.join(texts),tokenizer),cuts
                    stop=positions[lo-1][1]
                    for marker in chunking.MARKER.finditer(content):
                        if marker.start()<stop<marker.end():stop=marker.start()
                    if not content[:stop].strip():return selected,chunking.token_count('\n\n'.join(texts),tokenizer),cuts
                    end=start+stop;content=content[:stop];cuts+=1
                    selected.append(dict(row,inicio=start,fim=end,texto=content));texts.append(content)
                    assert chunking.token_count('\n\n'.join(texts),tokenizer)<=budget
                    return selected,chunking.token_count('\n\n'.join(texts),tokenizer),cuts
                selected.append(dict(row,inicio=start,fim=end,texto=content));texts.append(content);seen[ident].append((start,end))
    used=chunking.token_count('\n\n'.join(texts),tokenizer)
    assert used<=budget
    return selected,used,cuts


def prefix_for_encoder(row,tokenizer,limit):
    """Simulação explícita: nunca confundida com execução de embeddings."""
    extra=tokenizer.num_special_tokens_to_add(pair=False) if hasattr(tokenizer,'num_special_tokens_to_add') else 0
    spans=chunking.split_spans(row['texto'],tokenizer,max(16,limit-extra),0)
    a,b=spans[0]
    return dict(row,inicio=row['inicio']+a,fim=row['inicio']+b,texto=row['texto'][a:b])


def diagnose(question,top,all_rows,tokenizer):
    value=support_fraction(question,top)
    expected={r['registro_id'] for g in question['alternativas_suporte'] for r in g}
    doc_hit=any(r['registro_id'] in expected for r in top)
    split=False;wrong_section=[]
    for group in question['alternativas_suporte']:
        for ref in group:
            relevant=[r for r in all_rows if r['registro_id']==ref['registro_id'] and r['campo_texto']==ref['campo_texto']]
            if ref_fraction(ref,relevant)==1 and not any(ref_fraction(ref,[r])==1 for r in relevant):split=True
            if ref.get('secao_esperada'):
                found=[r for r in top if ref_fraction(ref,[r])>0 and r['secao'] not in ('nao_identificada','nao_classificada')]
                wrong_section.extend(r['secao']!=ref['secao_esperada'] for r in found)
    risks={}
    for limit in (512,8192):
        simulated=[prefix_for_encoder(r,tokenizer,limit) for r in top]
        risks[f'perda_suporte_simulada_encoder_{limit}']=max(0.,value-support_fraction(question,simulated))
    return dict(query_id=question['query_id'],suporte_fracao=value,
                acordao_errado=not doc_hit,trecho_errado=doc_hit and value==0,
                evidencia_atravessa_fronteira=split,evidencia_cortada_na_recuperacao=split and value<1,
                secao_mal_classificada=any(wrong_section) if wrong_section else None,
                truncamento_encoder_real='nao_aplicavel_encoder_nao_executado',**risks)


def paired(frame,seed=SEED,replicas=2000):
    """Reamostragem pareada de IDs de perguntas, nunca de chunks."""
    if frame.empty:return pd.DataFrame()
    output=[]
    for (scope,budget),group in frame.groupby(['escopo','orcamento']):
        pivot=group.pivot(index='query_id',columns='versao',values='suporte_fracao')
        for a,b in combinations(pivot.columns,2):
            both=pivot[[a,b]].dropna()
            if both.empty:
                output.append(dict(escopo=scope,orcamento=budget,a=a,b=b,n=0,status='sem_gabarito',vitorias=None,empates=None,derrotas=None,delta_media=None,ic95_inf=None,ic95_sup=None));continue
            delta=(both[a]-both[b]).to_numpy(float);rng=np.random.default_rng(seed)
            means=delta[rng.integers(0,len(delta),size=(replicas,len(delta)))].mean(axis=1)
            eps=1e-12
            output.append(dict(escopo=scope,orcamento=budget,a=a,b=b,n=len(delta),status='calculado',
                vitorias=int((delta>eps).sum()),empates=int((np.abs(delta)<=eps).sum()),derrotas=int((delta<-eps).sum()),
                delta_media=float(delta.mean()),ic95_inf=float(np.quantile(means,.025)),ic95_sup=float(np.quantile(means,.975)),
                seed=seed,replicas=replicas))
    return pd.DataFrame(output)


def assign_splits(queries,seed=SEED):
    groups=defaultdict(list)
    for q in queries:
        # Família temática evita repartir, por exemplo, perguntas de vínculo entre ajuste e teste.
        family=re.split(r'[(/]',q['tema'].casefold())[0].strip()
        groups[family].append(q['query_id'])
    keys=sorted(groups);rng=np.random.default_rng(seed);rng.shuffle(keys)
    target=math.ceil(len(queries)*.2);test=set()
    for key in keys:
        if len(test)>=target:break
        test.update(groups[key])
    return [dict(query_id=q['query_id'],familia_tematica=re.split(r'[(/]',q['tema'].casefold())[0].strip(),
                 particao='teste_final' if q['query_id'] in test else 'ajuste') for q in queries]


def prepare(root,max_docs=120,final=False):
    if final and (Path(root)/'avaliacao/dados/jurisprudencia/teste_final_iniciado.json').exists():
        raise ValueError('Teste final já iniciado; não repetir nem substituir sua execução.')
    state=base.prepare(root,max_docs);root=state['root']
    all_queries=state['queries'];splits=assign_splits(all_queries)
    partition='teste_final' if final else 'ajuste';ids={r['query_id'] for r in splits if r['particao']==partition}
    state['all_queries']=all_queries;state['queries']=[q for q in all_queries if q['query_id'] in ids]
    state['questions']=[q for q in state['questions'] if q['query_id'] in ids]
    for q in state['controls']:
        doc=next(d for d in state['fixtures'] if d['registro_id']==q['alternativas_suporte'][0][0]['registro_id'])
        q['alternativas_suporte']=[[original_reference(doc,g[0]['inicio'],g[0]['fim'],'fundamentacao' if i==0 else 'dispositivo')]
                                   for i,g in enumerate(q['alternativas_suporte'])]
    config=dict(state['config'],versao=3,parametros=PARAMS,particao_avaliada=partition,
                codigo_cobertura_sha256=audit.hash_file(cobertura_metricas.__file__),
                divisao_perguntas=splits,teste_final_ja_exposto_em_execucoes_exploratorias=True,
                tokenizer_backend_sha256=base.sha(state['tokenizer'].backend_tokenizer.to_str()),
                codigo_avancado_sha256=audit.hash_file(__file__),titulos=TITLES,
                corpus_documentos=[dict(registro_id=d['registro_id'],texto_sha256=base.sha(d['texto']),arquivo_sha256=d['parent_sha256']) for d in state['docs']],
                espaco_offsets='Documento-base inteiro protegido, anterior ao chunking; não são offsets nos arquivos brutos pré-PLN.')
    identity=base.sha(json.dumps(config,sort_keys=True,ensure_ascii=False))
    report=root/'dados/relatorios/jurisprudencia/chunking_avancado'/identity;data=root/'dados/chunks/jurisprudencia/avancado'/identity
    report.mkdir(parents=True,exist_ok=True);data.mkdir(parents=True,exist_ok=True)
    state.update(config=config,identity=identity,report=report,data=data,titles=TITLES,chunk_builder=build_chunks,
                 extended_results=[],budget_records=[],diagnostics=[],evidence_records=[],split_records=splits,partition=partition)
    audit.write_json(report/'configuracao.json',config);audit.write_json(report/'particoes_perguntas.json',splits)
    (report/'codigo_avancado_executado.py').write_bytes(Path(__file__).read_bytes())
    (report/'codigo_base_executado.py').write_bytes(Path(base.__file__).read_bytes())
    import pyarrow as pa
    import pyarrow.parquet as pq
    corpus=data/'documentos_base.parquet'
    pq.write_table(pa.Table.from_pylist([dict(registro_id=d['registro_id'],campo_texto=d['texto_principal_campo'],texto=d['texto'],texto_sha256=base.sha(d['texto'])) for d in state['docs']]),corpus,compression='zstd')
    audit.write_json(report/'manifesto_corpus.json',dict(arquivo=str(corpus.relative_to(root)),sha256=audit.hash_file(corpus),documentos=len(state['docs'])))
    # O teste final exige um congelamento separado e referências; nunca é executado como fallback.
    if final:
        if len(state['questions'])!=len(state['queries']):raise ValueError('Teste final exige evidências para todas as perguntas reservadas.')
        protocol=root/'avaliacao/dados/jurisprudencia/protocolo_congelado.json'
        if not protocol.exists():raise ValueError('Congele o protocolo após o ajuste antes de executar o teste final.')
        frozen=json.loads(protocol.read_text(encoding='utf-8'))
        expected=dict(parametros=PARAMS,csv_sha256=config['csv_perguntas_sha256'],corpus=config['corpus_documentos'],
                      codigo_avancado_sha256=config['codigo_avancado_sha256'],codigo_base_sha256=config['codigo_sha256'],
                      codigo_cobertura_sha256=config['codigo_cobertura_sha256'],
                      tokenizer_backend_sha256=config['tokenizer_backend_sha256'],particoes=splits)
        if frozen['protocolo']!=expected:raise ValueError('Protocolo/corpus divergem do congelamento.')
        lock=root/'avaliacao/dados/jurisprudencia/teste_final_iniciado.json'
        if lock.exists():raise ValueError('Teste final já iniciado; não repetir nem substituir sua execução.')
        with lock.open('x',encoding='utf-8') as stream:json.dump(dict(protocolo_sha256=base.sha(json.dumps(expected,sort_keys=True)),pasta_relatorios=str(report.relative_to(root))),stream)
    return state


def freeze(state):
    if state['partition']!='ajuste':raise ValueError('Somente ajuste pode congelar o protocolo.')
    if not state.get('complete'):raise ValueError('Conclua a execução de ajuste antes de congelar.')
    c=state['config'];protocol=dict(parametros=PARAMS,csv_sha256=c['csv_perguntas_sha256'],corpus=c['corpus_documentos'],
                codigo_avancado_sha256=c['codigo_avancado_sha256'],codigo_base_sha256=c['codigo_sha256'],
                codigo_cobertura_sha256=c['codigo_cobertura_sha256'],
                tokenizer_backend_sha256=c['tokenizer_backend_sha256'],particoes=state['split_records'])
    path=state['root']/'avaliacao/dados/jurisprudencia/protocolo_congelado.json'
    value=dict(protocolo=protocol,sha256=base.sha(json.dumps(protocol,sort_keys=True)),
               observacao='Divisão prospectiva: perguntas já expostas exploratoriamente; não é teste cego inédito.')
    if path.exists() and json.loads(path.read_text(encoding='utf-8'))!=value:raise ValueError('Já existe outro protocolo congelado.')
    audit.write_json(path,value);return path


def experiment(state,version):
    frame,stats,controls=base.experiment(state,version)
    rows=state['chunks'][version];documents={d['registro_id']:d for d in state['docs']}
    unit=unit_audit(rows,documents,state['tokenizer']);unit.update(versao=version)
    audit.write_json(state['report']/(version+'_auditoria_unidades.json'),unit)
    state['extended_results'].append(unit)
    for scope,docs,questions,queries,allrows in [
        ('jurisprudencia_ajuste' if state['partition']=='ajuste' else 'jurisprudencia_teste_final',documents,state['questions'],state['queries'],rows),
        ('controle_sintetico',{d['registro_id']:d for d in state['fixtures']},state['controls'],state['controls'],
         [r for d in state['fixtures'] for r in build_chunks(d,version,state['tokenizer'])])]:
        annotated={q['query_id']:q for q in questions};searcher=base.BM25(allrows)
        for query in queries:
            ranking=searcher.search(query['pergunta'],50);q=annotated.get(query['query_id'])
            if q:
                diagnosis=diagnose(q,ranking[:5],allrows,state['tokenizer'])
                evidence=dict(cobertura_metricas.evidence_units(q,allrows,ranking),
                    **cobertura_metricas.truncation_rates(q,allrows,state['tokenizer']))
            else:diagnosis=dict(query_id=query['query_id'],suporte_fracao=None,status='sem_evidencia_anotada',
                acordao_errado=None,trecho_errado=None,evidencia_cortada_na_recuperacao=None,secao_mal_classificada=None,
                truncamento_encoder_real='nao_aplicavel_encoder_nao_executado')
            if not q:
                evidence=dict(unidades_necessarias_minimas=None,unidades_ranqueadas_ate_cobrir=None,evidencia_fragmentada=None,
                    taxa_truncamento_encoder_real=None,estado_encoder='nao_executado_bm25')
                for limit in (512,8192):
                    evidence[f'evidencia_truncada_encoder_{limit}_simulado']=None
                    evidence[f'evidencia_perdida_encoder_{limit}_simulado']=None
            state['evidence_records'].append(dict(versao=version,escopo=scope,query_id=query['query_id'],**evidence))
            state['diagnostics'].append(dict(versao=version,escopo=scope,**diagnosis))
            for budget in BUDGETS:
                context,used,cuts=context_at_budget(ranking,docs,state['tokenizer'],budget)
                value=support_fraction(q,context) if q else None
                before=support_fraction(q,ranking) if q else None
                state['budget_records'].append(dict(versao=version,escopo=scope,query_id=query['query_id'],orcamento=budget,
                    tokens_utilizados=used,suporte_fracao=value,suporte_completo=int(value>=1-1e-12) if value is not None else None,
                    cobertura_T=value,
                    suporte_antes_montagem=before,perda_suporte_montagem=max(0.,before-value) if q else None,
                    cortes_explicitos_contexto=cuts,status='avaliado' if q else 'sem_evidencia_anotada'))
    return frame,dict(stats,**unit),controls


def finish(state):
    import matplotlib.pyplot as plt
    if set(state['chunks'])!=set(TITLES):raise ValueError('Faltam variantes na comparação.')
    expected_documents={d['registro_id'] for d in state['docs']}
    if any({r['registro_id'] for r in rows}!=expected_documents for rows in state['chunks'].values()):
        raise ValueError('As variantes não usam os mesmos documentos.')
    # Sem perguntas finais circulando na execução de ajuste.
    permitted={r['query_id'] for r in state['split_records'] if r['particao']==state['partition']}
    assert {q['query_id'] for q in state['queries']}==permitted
    curves=pd.DataFrame(state['budget_records']);stats=paired(curves)
    main_metric=cobertura_metricas.summarize_2500(curves)
    evidence_summary=cobertura_metricas.aggregate_evidence(state['evidence_records'])
    main_metric.to_csv(state['report']/'cobertura_2500_resumo.csv',index=False,encoding='utf-8-sig')
    audit.write_json(state['report']/'cobertura_2500_resumo.json',json.loads(main_metric.to_json(orient='records')))
    audit.write_json(state['report']/'fragmentacao_unidades_truncamento.json',json.loads(evidence_summary.to_json(orient='records')))
    audit.write_json(state['report']/'evidencias_por_pergunta.json',state['evidence_records'])
    curves.to_csv(state['report']/'cobertura_por_pergunta_orcamento.csv',index=False,encoding='utf-8-sig')
    curves.to_csv(state['report']/'suporte_por_pergunta_orcamento.csv',index=False,encoding='utf-8-sig')
    stats.to_csv(state['report']/'comparacao_pareada_bootstrap.csv',index=False,encoding='utf-8-sig')
    audit.write_json(state['report']/'diagnostico_falhas.json',state['diagnostics'])
    audit.write_json(state['report']/'auditoria_unidades.json',state['extended_results'])
    if not stats.empty:
        pivot=curves.pivot(index=['escopo','orcamento','query_id'],columns='versao',values='suporte_fracao').apply(pd.to_numeric,errors='coerce')
        by_query=[]
        for a,b in combinations(TITLES,2):
            for (scope,budget,qid),row in pivot.iterrows():
                delta=row[a]-row[b]
                by_query.append(dict(escopo=scope,orcamento=budget,query_id=qid,a=a,b=b,
                    resultado='sem_gabarito' if pd.isna(delta) else 'vitoria' if delta>1e-12 else 'derrota' if delta< -1e-12 else 'empate',
                    delta=None if pd.isna(delta) else float(delta)))
        audit.write_json(state['report']/'vitorias_empates_derrotas_por_pergunta.json',by_query)
    fig,axes=plt.subplots(1,2,figsize=(13,4.5))
    for scope,ax,title in [('controle_sintetico',axes[0],'Controle fictício: Cobertura@T'),
                           ('jurisprudencia_ajuste' if state['partition']=='ajuste' else 'jurisprudencia_teste_final',axes[1],'Jurisprudência: Cobertura@T')]:
        subset=curves[curves.escopo.eq(scope)]
        for version,title_version in TITLES.items():
            group=subset[subset.versao.eq(version)].groupby('orcamento').suporte_fracao.mean()
            if group.notna().any():ax.plot(group.index,group.values,marker='o',label=version)
        ax.axvline(2500,color='gray',linestyle='--',alpha=.6)
        ax.set(xlabel='T — orçamento máximo de tokens',ylabel='Cobertura média da evidência',title=title,ylim=(0,1.05));ax.set_xticks(BUDGETS)
        if subset.suporte_fracao.notna().any():ax.legend(fontsize=7)
        else:ax.text(.5,.5,'Curva indisponível sem evidências anotadas.\nBuscas e consumo de contexto foram executados.',transform=ax.transAxes,ha='center')
    fig.tight_layout();fig.savefig(state['report']/'curvas_suporte_tokens.png',dpi=140);plt.show()
    audit_frame=pd.DataFrame(state['extended_results'])
    fig,axes=plt.subplots(1,2,figsize=(12,4))
    audit_frame.plot.barh(x='versao',y=['acima_512','acima_8192'],ax=axes[0]);axes[0].set_title('Unidades acima dos limites (sem encoder)')
    audit_frame.plot.barh(x='versao',y='vetores_planejados',ax=axes[1],legend=False);axes[1].set_title('Vetores planejados — gerados: zero (BM25)')
    fig.tight_layout();fig.savefig(state['report']/'auditoria_limites_vetores.png',dpi=140);plt.show()
    summary=dict(configuracao=state['config'],resultados=state['results'],auditoria_unidades=state['extended_results'],
                 perguntas_csv_total=len(state['all_queries']),perguntas_particao_executada=len(state['queries']),
                 perguntas_com_suporte=len(state['questions']),particao_executada=state['partition'],
                 numero_estrategias=6,bootstrap_seed=SEED,bootstrap_replicas=2000,
                 teste_final_executado=state['partition']=='teste_final',encoder_executado=False,
                 numero_vetores_gerados=0,estado='concluido',
                 metrica_principal='Cobertura@T',resumo_principal='Cobertura média em T=2500',
                 limites=('Gabarito real ausente: curvas e inferência de qualidade reais indisponíveis. ' if not state['questions'] else '')+
                         'Controles fictícios não estimam qualidade real. Corpus de desenvolvimento amostral.')
    audit.write_json(state['report']/'resumo.json',summary)
    audit.write_json(state['root']/'dados/relatorios/jurisprudencia/chunking_avancado/ativa.json',dict(pasta_relatorios=str(state['report'].relative_to(state['root'])),pasta_dados=str(state['data'].relative_to(state['root']))))
    state['complete']=True
    return curves,stats,audit_frame
