"""Teste reservado de finalistas congeladas: sem nova seleção e com checkpoints por consulta."""
from pathlib import Path
import json,os,sqlite3,hashlib
from importlib.metadata import version as package_version
import numpy as np,pandas as pd
from . import audit,chunking_suporte as base,chunking_avancado as adv,chunking
from . import contexto_centrado as context,piloto_bge,perguntas_csv,finalistas_chunking as adjustment

def canonical(value):return base.sha(json.dumps(value,sort_keys=True,ensure_ascii=False))

def source_available(question,documents):
    return any(all(ref['registro_id'] in documents for ref in group) for group in question.get('alternativas_suporte',[]))

def environment_versions():
    return {name:package_version(name) for name in ('torch','transformers','sentence-transformers','numpy','pandas','pyarrow')}

def document_vector_fingerprint(root,rows):
    db=sqlite3.connect(Path(root)/'dados/chunks/jurisprudencia/cache_bge'/(piloto_bge.REVISION+'_float32_8192.sqlite'))
    records=[]
    for r in rows:
        item=db.execute('SELECT vector FROM embeddings WHERE hash=?',(r['texto_sha256'],)).fetchone()
        if item is None:raise ValueError('Vetor de documento ausente antes do teste final.')
        values=np.frombuffer(item[0],dtype=np.float32)
        assert values.shape==(1024,) and np.isfinite(values).all() and abs(np.linalg.norm(values)-1)<1e-5
        records.append([r['chunk_id'],r['texto_sha256'],hashlib.sha256(item[0]).hexdigest()])
    db.close();return canonical(records)

def load_protocol(root):
    root=Path(root);p=root/'avaliacao/dados/jurisprudencia/protocolo_congelado.json'
    if not p.exists():raise ValueError('Congele os parâmetros e o corpus após o ajuste, antes de acessar o teste.')
    value=json.loads(p.read_text(encoding='utf-8'));assert canonical(value['protocolo'])==value['sha256']
    return value

def freeze(root):
    root=Path(root)
    pointer=json.loads((root/'dados/relatorios/jurisprudencia/finalistas/ativa.json').read_text(encoding='utf-8'))
    report=root/pointer['pasta_relatorios'];data=root/pointer['pasta_dados']
    cfg=json.loads((report/'configuracao.json').read_text(encoding='utf-8'))
    assert cfg['codigo_sha256']==audit.hash_file(adjustment.__file__)
    assert cfg['gabarito_sha256']==audit.hash_file(root/'avaliacao/dados/jurisprudencia/perguntas_suporte.jsonl')
    selected=json.loads((report/'finalistas_selecionadas.json').read_text(encoding='utf-8'));assert len(selected)==2
    import pyarrow.parquet as pq
    indices=[]
    for finalist in selected:
        index=finalist['versao'] if finalist['familia']=='fixa' else '_paragrafo_index'
        file=data/(index+'.parquet');rows=pq.read_table(file).to_pylist()
        indices.append(dict(versao=finalist['versao'],indice=index,arquivo=str(file.relative_to(root)),sha256=audit.hash_file(file),
            vetores_sha256=document_vector_fingerprint(root,rows)))
    olddata=root/cfg['origem_dados'];corpus=olddata/'documentos_base.parquet'
    assert audit.hash_file(corpus)==cfg['corpus_sha256']
    held=json.loads((root/'avaliacao/dados/jurisprudencia/reserva_piloto_congelada.json').read_text(encoding='utf-8'))
    from . import light_nlp
    _,protected_sources=light_nlp.load(root)
    protocol=dict(versao=7,particao='teste_final',query_ids=held['perguntas_reservadas'],
        perguntas_sha256=held['conteudo_reservado_sha256'],finalistas=selected,
        indices=indices,
        relatorio_ajuste=str(report.relative_to(root)),dados_ajuste=str(data.relative_to(root)),
        arquivo_corpus=str(corpus.relative_to(root)),corpus_sha256=cfg['corpus_sha256'],
        gabarito_ajuste_sha256=cfg['gabarito_sha256'],selecao_ajuste_sha256=audit.hash_file(report/'finalistas_selecionadas.json'),
        orcamentos=list(adv.BUDGETS),orcamento_primario=2500,seed=adv.SEED,bootstrap_replicas=2000,
        metrica='Cobertura@T por caracteres, melhor alternativa completa; intervalos fora do corpus têm cobertura zero e perguntas compostas podem ter cobertura parcial.',
        metrica_secundaria='Disponibilidade completa de alguma alternativa de gabarito no índice e Cobertura@2500 condicionada a essa disponibilidade, sem substituir a métrica global.',
        regra_gold='Intervalos em fundamento e resultado próprios ou ementa própria equivalente; sem validar como decisão a alegação de parte ou julgamento reformado.',
        controles='Consultas comportamentais/outro domínio são executadas, mas não recebem nota de suporte jurídico inventada.',
        corpus_politica='18 documentos congelados antes da inspeção das perguntas; referências externas para gabarito não são acrescentadas ao índice.',
        fontes_referencia=[{k:f[k] for k in ('arquivo_id','arquivo','sha256')} for f in protected_sources['arquivos']],
        tipo_reserva='Reserva prospectiva; o protocolo anterior registrou exposição em buscas exploratórias anteriores ao congelamento.',
        modelo=piloto_bge.MODEL,revisao=piloto_bge.REVISION,dtype='float32',dimensao=1024,max_length=8192,
        bibliotecas=environment_versions(),
        codigos={name:audit.hash_file(module) for name,module in [('teste_final',__file__),('finalistas',adjustment.__file__),
            ('contexto',context.__file__),('metricas',adv.__file__),('chunking',chunking.__file__),('encoder',piloto_bge.__file__)]})
    value=dict(protocolo=protocol,sha256=canonical(protocol),fase='parâmetros e corpus congelados antes da anotação e avaliação reservada')
    path=root/'avaliacao/dados/jurisprudencia/protocolo_congelado.json'
    if path.exists():
        if json.loads(path.read_text(encoding='utf-8'))!=value:raise ValueError('Já existe outro congelamento; não sobrescrever.')
    else:
        with path.open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2)
    return path

def reserved_for_annotation(root):
    root=Path(root);frozen=load_protocol(root);protocol=frozen['protocolo'];queries,_=perguntas_csv.load(root)
    byid={q['query_id']:q for q in queries}
    for qid in protocol['query_ids']:assert canonical(byid[qid])==protocol['perguntas_sha256'][qid]
    path=root/'avaliacao/dados/jurisprudencia/curadoria_teste_final_iniciada.json'
    value=dict(protocolo_sha256=frozen['sha256'],etapa='anotação de referências antes da busca das finalistas; parâmetros não serão ajustados')
    if path.exists():assert json.loads(path.read_text(encoding='utf-8'))==value
    else:audit.write_json(path,value)
    return [byid[qid] for qid in protocol['query_ids']]

def prepare(root):
    root=Path(root);frozen=load_protocol(root);p=frozen['protocolo']
    assert environment_versions()==p['bibliotecas'],'Ambiente alterado após o congelamento.'
    for name,module in [('teste_final',__file__),('finalistas',adjustment.__file__),('contexto',context.__file__),
                        ('metricas',adv.__file__),('chunking',chunking.__file__),('encoder',piloto_bge.__file__)]:
        assert p['codigos'][name]==audit.hash_file(module),'Código alterado após congelamento.'
    assert audit.hash_file(root/p['arquivo_corpus'])==p['corpus_sha256']
    assert audit.hash_file(root/'avaliacao/dados/jurisprudencia/perguntas_suporte.jsonl')==p['gabarito_ajuste_sha256']
    queries=reserved_for_annotation(root);goldpath=root/'avaliacao/dados/jurisprudencia/perguntas_suporte_teste_final.jsonl'
    if not goldpath.exists():raise ValueError('Anote os gabaritos reservados antes da busca das finalistas.')
    gold=[json.loads(x) for x in goldpath.read_text(encoding='utf-8').splitlines() if x.strip()]
    assert {q['query_id'] for q in gold}==set(p['query_ids']) and len(gold)==7
    byid={q['query_id']:q for q in queries}
    for q in gold:assert q['pergunta']==byid[q['query_id']]['pergunta']
    import pyarrow.parquet as pq
    from transformers import AutoTokenizer
    docs={d['registro_id']:dict(d,texto_principal_campo=d['campo_texto']) for d in pq.read_table(root/p['arquivo_corpus']).to_pylist()}
    referencepath=root/'avaliacao/dados/jurisprudencia/referencias_teste_final.parquet'
    refs=pq.read_table(referencepath).to_pylist() if referencepath.exists() else []
    reference_docs=dict(docs)
    verified_sources=set()
    for d in refs:
        assert d['registro_id'] not in docs or base.sha(d['texto'])==base.sha(docs[d['registro_id']]['texto'])
        if d['registro_id'] not in docs:
            source=next(f for f in p['fontes_referencia'] if f['arquivo']==d['parent_arquivo'])
            assert source['sha256']==d['parent_sha256']
            if source['arquivo'] not in verified_sources:
                assert audit.hash_file(root/source['arquivo'])==source['sha256'];verified_sources.add(source['arquivo'])
        reference_docs[d['registro_id']]=dict(d,texto_principal_campo=d['campo_texto'])
    eligible=[q for q in gold if q.get('avaliacao','suporte_intervalos')=='suporte_intervalos']
    base.validate_questions(eligible,reference_docs)
    tokenizer=AutoTokenizer.from_pretrained(p['modelo'],revision=p['revisao'],local_files_only=True,use_fast=True)
    units={};variants={}
    for finalist in p['finalistas']:
        name=finalist['versao']
        if finalist['familia']=='fixa':index=name;cap=None
        else:index='_paragrafo_index';cap=int(name.rsplit('_',1)[1])
        fingerprint=next(f for f in p['indices'] if f['versao']==name)
        assert audit.hash_file(root/fingerprint['arquivo'])==fingerprint['sha256']
        if index not in units:units[index]=pq.read_table(root/fingerprint['arquivo']).to_pylist()
        assert document_vector_fingerprint(root,units[index])==fingerprint['vetores_sha256']
        assert {r['registro_id'] for r in units[index]}==set(docs)
        variants[name]=(index,cap)
    config=dict(protocolo_sha256=frozen['sha256'],gabarito_sha256=audit.hash_file(goldpath),
        referencias_sha256=audit.hash_file(referencepath) if referencepath.exists() else None)
    identity=canonical(config);report=root/'dados/relatorios/jurisprudencia/teste_final'/identity;report.mkdir(parents=True,exist_ok=True)
    audit.write_json(report/'configuracao.json',dict(config,protocolo=p))
    (report/'gabarito_snapshot.jsonl').write_bytes(goldpath.read_bytes())
    if referencepath.exists():(report/'referencias_manifesto.json').write_text(json.dumps(dict(arquivo=str(referencepath.relative_to(root)),sha256=audit.hash_file(referencepath))),encoding='utf-8')
    return dict(root=root,report=report,questions=queries,gold=gold,eligible=eligible,docs=docs,reference_docs=reference_docs,
        units=units,variants=variants,tokenizer=tokenizer,config=dict(config,tokenizador_sha256=base.sha(tokenizer.backend_tokenizer.to_str())),
        protocol=p,identity=identity)

def run(root,resume=False):
    root=Path(root);os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
    state=prepare(root);lock=root/'avaliacao/dados/jurisprudencia/teste_final_iniciado.json'
    record=dict(protocolo_sha256=state['config']['protocolo_sha256'],gabarito_sha256=state['config']['gabarito_sha256'],
        relatorio=str(state['report'].relative_to(root)),identidade=state['identity'])
    if lock.exists():
        old=json.loads(lock.read_text(encoding='utf-8'))
        if old!=record:raise ValueError('Outro teste final já foi iniciado; não substituir.')
        if (state['report']/'concluido.json').exists():raise ValueError('Teste final concluído. Leia as saídas; não execute novamente.')
        if not resume:raise ValueError('Teste iniciado; use retomada explícita, com mesmos arquivos, para completar checkpoints pendentes.')
    else:
        with lock.open('x',encoding='utf-8') as f:json.dump(record,f,ensure_ascii=False,indent=2)
    vectors,views=piloto_bge.encode(state)
    enc=json.loads((state['report']/'execucao_encoder.json').read_text(encoding='utf-8'))
    enc.update(particao='teste_final',reserva_codificada=True,observacao='Metadados de partição aplicados pelo executor do teste; o helper legado é compartilhado com ajuste.')
    audit.write_json(state['report']/'execucao_encoder.json',enc)
    packer=context.Packer(state['docs'],state['tokenizer']);gold={q['query_id']:q for q in state['gold']};records=[];ranklog=[];contexts=[]
    for version,(index,cap) in state['variants'].items():
        rows=state['units'][index];matrix=np.stack([vectors[r['texto_sha256']] for r in rows])
        for q in state['questions']:
            checkpoint=state['report']/('consulta_'+version+'_'+q['query_id']+'.json')
            if checkpoint.exists():saved=json.loads(checkpoint.read_text(encoding='utf-8'))
            else:
                scores=matrix@vectors[base.sha(q['pergunta'])];order=sorted(range(len(rows)),key=lambda i:(-float(scores[i]),rows[i]['chunk_id']))
                rank=[dict(rows[i],rank=j+1,score=float(scores[i])) for j,i in enumerate(order)]
                g=gold[q['query_id']];eligible=g.get('avaliacao','suporte_intervalos')=='suporte_intervalos'
                expected={r['registro_id'] for group in g.get('alternativas_suporte',[]) for r in group}
                present=source_available(g,state['docs']) if eligible else None
                saved=dict(curves=[],ranking=[{k:r[k] for k in ('chunk_id','registro_id','rank','score','inicio','fim')} for r in rank[:10]],contexts=[])
                for budget in state['protocol']['orcamentos']:
                    selected,used,cuts,examined=packer.pack(rank,budget,window_tokens=cap)
                    saved['curves'].append(dict(query_id=q['query_id'],versao=version,orcamento=budget,
                        cobertura=adv.support_fraction(g,selected) if eligible else None,
                        documento_suporte_no_corpus=present,avaliacao=g.get('avaliacao','suporte_intervalos'),
                        tokens_utilizados=used,unidades_distintas=len({r['chunk_id'] for r in selected}),cortes=cuts,examinadas=examined))
                    if budget==2500:saved['contexts']=[{k:r[k] for k in ('chunk_id','registro_id','inicio','fim','rank')} for r in selected]
                audit.write_json(checkpoint,saved)
            records.extend(saved['curves']);ranklog.extend([dict(query_id=q['query_id'],versao=version,**r) for r in saved['ranking']])
            contexts.extend([dict(query_id=q['query_id'],versao=version,**r) for r in saved['contexts']])
            print('Teste reservado concluído:',q['query_id'],version,flush=True)
    frame=pd.DataFrame(records);frame.to_csv(state['report']/'cobertura.csv',index=False)
    pd.DataFrame(ranklog).to_csv(state['report']/'ranking_top10.csv',index=False);pd.DataFrame(contexts).to_csv(state['report']/'contextos_2500.csv',index=False)
    valid=frame[frame.cobertura.notna()];primary=valid[valid.orcamento==2500].groupby('versao').agg(
        cobertura_2500=('cobertura','mean'),perguntas_com_intervalo=('query_id','size'),
        perguntas_fonte_no_corpus=('documento_suporte_no_corpus','sum')).reset_index()
    primary.to_csv(state['report']/'resumo_2500.csv',index=False)
    pairedframe=valid.assign(recuperador='BGE-M3');pairs=adjustment.paired(pairedframe)
    if len(pairs.columns)==0:pairs=pd.DataFrame(columns=['a','b','n','vitorias','empates','derrotas','delta_media','ic95_inf','ic95_sup','seed','replicas'])
    pairs.to_csv(state['report']/'bootstrap_final.csv',index=False)
    assert audit.hash_file(root/state['protocol']['arquivo_corpus'])==state['protocol']['corpus_sha256']
    audit.write_json(state['report']/'concluido.json',dict(status='teste_final_concluido',consultas=7,finalistas=2,
        gabaritos_com_intervalos=len(state['eligible']),repetido=False,protocolo_sha256=state['config']['protocolo_sha256']))
    audit.write_json(root/'dados/relatorios/jurisprudencia/teste_final/ativa.json',dict(pasta_relatorios=str(state['report'].relative_to(root)),identidade=state['identity']))
    return primary
