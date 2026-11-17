"""Comparação complementar em corpus enriquecido; não substitui o teste consumido."""
from pathlib import Path
import json, os
import numpy as np
import pandas as pd
from . import audit, chunking, chunking_suporte as base, chunking_avancado as adv
from . import contexto_centrado as context, piloto_bge, perguntas_csv
from . import finalistas_chunking as finalists, teste_final_chunking as final
from . import experimento_orcamento as experiment


def read_jsonl(path):
    return [json.loads(x) for x in Path(path).read_text(encoding='utf-8').splitlines() if x.strip()]


def merge_documents(groups):
    """Não permita que uma cópia diferente reutilize o identificador de documento."""
    docs = {}
    for group in groups:
        for d in group:
            if d['registro_id'] in docs:
                old = docs[d['registro_id']]
                if old['texto'] != d['texto'] or old['campo_texto'] != d['campo_texto']:
                    raise ValueError('Mesmo identificador com texto/campo divergente.')
            else:
                docs[d['registro_id']] = d
    return dict(sorted(docs.items()))


def audit_units(rows, docs, tokenizer):
    """A reconstrução aceita sobreposição, mas não lacunas ou caracteres alterados."""
    assert {r['registro_id'] for r in rows} == set(docs)
    overlaps = 0
    for ident, doc in docs.items():
        cursor = 0
        for r in sorted((r for r in rows if r['registro_id'] == ident), key=lambda r:r['inicio']):
            assert 0 <= r['inicio'] <= cursor < r['fim'] <= len(doc['texto'])
            assert doc['texto'][r['inicio']:r['fim']] == r['texto']
            assert base.sha(r['texto']) == r['texto_sha256']
            assert r['tokens'] == chunking.token_count(r['texto'], tokenizer)
            assert r['metodo_fronteira']
            overlaps += max(0, cursor-r['inicio'])
            cursor = r['fim']
        assert cursor == len(doc['texto'])
    counts = pd.Series([r['tokens'] for r in rows], dtype=float)
    return dict(vetores=len(rows), textos_unicos=len({r['texto_sha256'] for r in rows}),
                mediana=float(counts.median()), p90=float(counts.quantile(.9)), maximo=int(counts.max()),
                acima_512=int((counts>512).sum()), acima_8192=int((counts>8192).sum()),
                caracteres_sobrepostos=overlaps, reconstrucao_sem_lacunas=True)


def prepare(root):
    root = Path(root).resolve()
    os.environ['HF_HUB_OFFLINE']='1'; os.environ['TRANSFORMERS_OFFLINE']='1'
    import pyarrow as pa, pyarrow.parquet as pq
    from transformers import AutoTokenizer
    frozen = final.load_protocol(root); p=frozen['protocolo']
    prior_pointer=json.loads((root/'dados/relatorios/jurisprudencia/teste_final/ativa.json').read_text(encoding='utf-8'))
    prior=root/prior_pointer['pasta_relatorios']
    assert (prior/'concluido.json').exists(), 'A avaliação complementar não consome nem substitui a reserva.'
    assert audit.hash_file(root/p['arquivo_corpus'])==p['corpus_sha256']
    metadata={r['registro_id']:r for r in pq.read_table(root/p['indices'][1]['arquivo']).to_pylist()}
    olddocs=[]
    for d in pq.read_table(root/p['arquivo_corpus']).to_pylist():
        olddocs.append(dict(metadata[d['registro_id']], **d, texto_principal_campo=d['campo_texto']))
    candidatepath=root/'avaliacao/dados/jurisprudencia/curadoria_teste_final/candidatos.jsonl'
    candidates=read_jsonl(candidatepath)
    sources={s['arquivo']:s for s in p['fontes_referencia']}
    verified=set(); external=[]
    for d in candidates:
        src=sources[d['parent_arquivo']]
        assert d['parent_sha256']==src['sha256']
        if src['arquivo'] not in verified:
            assert audit.hash_file(root/src['arquivo'])==src['sha256']
            verified.add(src['arquivo'])
        # Confere o próprio conteúdo na origem protegida, não só o manifesto.
        source=pq.read_table(root/src['arquivo'],filters=[('registro_id','=',d['registro_id'])],columns=[d['campo_texto']]).to_pylist()
        assert len(source)==1 and source[0][d['campo_texto']]==d['texto']
        external.append(dict(d,texto_principal_campo=d['campo_texto'],split_proposto='complementar',grupo_avaliacao='complementar'))
    docs=merge_documents([olddocs,external])
    devpath=root/'avaliacao/dados/jurisprudencia/perguntas_suporte.jsonl'
    reservedpath=root/'avaliacao/dados/jurisprudencia/perguntas_suporte_teste_final.jsonl'
    assert audit.hash_file(devpath)==p['gabarito_ajuste_sha256']
    assert audit.hash_file(reservedpath)==json.loads((prior/'configuracao.json').read_text(encoding='utf-8'))['gabarito_sha256']
    gold=read_jsonl(devpath)+read_jsonl(reservedpath)
    eligible=[q for q in gold if q.get('avaliacao','suporte_intervalos')=='suporte_intervalos']
    base.validate_questions(eligible,docs)
    queries,_=perguntas_csv.load(root)
    selected=p['finalistas']; assert {f['versao'] for f in selected}=={'fixa_500_o100','paragrafo_janela_500'}
    tokenizer=AutoTokenizer.from_pretrained(p['modelo'],revision=p['revisao'],local_files_only=True,use_fast=True)
    modules=[__file__,context.__file__,adv.__file__,base.__file__,finalists.__file__,piloto_bge.__file__,experiment.__file__]
    manifest=[dict(registro_id=d['registro_id'],texto_sha256=base.sha(d['texto']),campo_texto=d['campo_texto'],
        parent_arquivo=d['parent_arquivo'],parent_sha256=d['parent_sha256'],
        origem_corpus='piloto_original' if d['registro_id'] in metadata else 'lote_candidatos_completo') for d in docs.values()]
    config=dict(versao=8,tipo='avaliacao_complementar_pos_teste; perguntas já expostas; não é novo teste cego',
        regra_corpus='União integral dos 18 documentos anteriores e de TODOS os candidatos de referência já levantados. Sem seleção por score ou desempenho das finalistas.',
        documentos=manifest,documentos_total=len(docs),documentos_anteriores=len(olddocs),candidatos_linhas=len(candidates),
        candidatos_sha256=audit.hash_file(candidatepath),finalistas=selected,protocolo_anterior_sha256=frozen['sha256'],
        marcador_teste_anterior_sha256=audit.hash_file(root/'avaliacao/dados/jurisprudencia/teste_final_iniciado.json'),
        gabarito_ajuste_sha256=audit.hash_file(devpath),gabarito_reservado_sha256=audit.hash_file(reservedpath),
        perguntas_sha256=final.canonical(queries),query_ids=[q['query_id'] for q in queries],
        coorte_primaria=p['query_ids'],coorte_ajuste=[q['query_id'] for q in read_jsonl(devpath)],
        orcamentos=list(adv.BUDGETS),orcamento_primario=2500,seed=adv.SEED,bootstrap_replicas=2000,
        recuperador_primario='BGE-M3',recuperador_secundario='BM25',
        modelo=piloto_bge.MODEL,revisao=piloto_bge.REVISION,limite_encoder=8192,
        tokenizador_sha256=base.sha(tokenizer.backend_tokenizer.to_str()),
        codigos={Path(m).name:audit.hash_file(m) for m in modules})
    ident=final.canonical(config)
    report=root/'dados/relatorios/jurisprudencia/complementar'/ident; data=root/'dados/chunks/jurisprudencia/complementar'/ident
    report.mkdir(parents=True,exist_ok=True);data.mkdir(parents=True,exist_ok=True)
    configfile=report/'configuracao.json'
    if configfile.exists():assert json.loads(configfile.read_text(encoding='utf-8'))==config
    else:audit.write_json(configfile,config)
    units={}
    for f in selected:
        name=f['versao']; index=name if f['familia']=='fixa' else '_paragrafo_index'
        file=data/(index+'.parquet')
        if file.exists():rows=pq.read_table(file).to_pylist()
        else:
            rows=[]
            for d in docs.values():
                para=adv.build_chunks(d,'paragrafo',tokenizer)
                rows.extend(finalists.make_fixed(d,para[0],tokenizer,500,100) if f['familia']=='fixa' else para)
            pq.write_table(pa.Table.from_pylist(rows),file,compression='zstd')
        units[index]=rows
    checks=[dict(indice=k,**audit_units(rows,docs,tokenizer)) for k,rows in units.items()]
    pd.DataFrame(checks).to_csv(report/'auditoria_unidades.csv',index=False)
    corpus=data/'documentos_base.parquet'
    if not corpus.exists():
        fields=('registro_id','texto','campo_texto','texto_principal_campo','tribunal','arquivo_id','parent_arquivo','parent_sha256')
        pq.write_table(pa.Table.from_pylist([{k:d.get(k) for k in fields} for d in docs.values()]),corpus,compression='zstd')
    assert {d['registro_id']:d['texto'] for d in pq.read_table(corpus).to_pylist()}=={i:d['texto'] for i,d in docs.items()}
    (report/'gabarito_snapshot.jsonl').write_text(''.join(json.dumps(q,ensure_ascii=False)+'\n' for q in gold),encoding='utf-8')
    lock=dict(configuracao_sha256=audit.hash_file(configfile),corpus_sha256=audit.hash_file(corpus),
        gabarito_sha256=audit.hash_file(report/'gabarito_snapshot.jsonl'),
        indices={k:audit.hash_file(data/(k+'.parquet')) for k in units})
    protocol=report/'protocolo_complementar.json'
    if protocol.exists():assert json.loads(protocol.read_text(encoding='utf-8'))==lock
    else:audit.write_json(protocol,lock)
    audit.write_json(root/'dados/relatorios/jurisprudencia/complementar/ativa.json',dict(pasta_relatorios=str(report.relative_to(root)),pasta_dados=str(data.relative_to(root)),identidade=ident))
    print('Corpus complementar:',len(docs),'documentos;',len(queries),'consultas;',len(eligible),'gabaritos por intervalo.',flush=True)
    return dict(root=root,report=report,data=data,docs=docs,questions=queries,gold=gold,units=units,tokenizer=tokenizer,config=config)


def cohort(qid, config):
    return 'reserva_ja_exposta' if qid in config['coorte_primaria'] else 'ajuste_anterior'


def compare(frame, primary_ids):
    """Bootstrap entre as duas finalistas por recuperador; nunca misture ajuste e reserva."""
    out=[]
    for scope, ids in [('reserva_ja_exposta',set(primary_ids)),('ajuste_anterior',set(frame.query_id)-set(primary_ids))]:
        subset=frame[frame.query_id.isin(ids)]
        for r, group in subset.groupby('recuperador'):
            pairs=finalists.paired(group)
            for row in pairs.to_dict('records'):out.append(dict(coorte=scope,recuperador=r,**row))
    return pd.DataFrame(out)


def run(root):
    state=prepare(root);report=state['report']
    if (report/'concluido.json').exists():
        raise ValueError('Avaliação complementar já concluída. Leia os resultados salvos.')
    audit.write_json(report/'iniciado.json',dict(protocolo_sha256=audit.hash_file(report/'protocolo_complementar.json')))
    vectors,views=piloto_bge.encode(state)
    enc=json.loads((report/'execucao_encoder.json').read_text(encoding='utf-8'))
    enc.update(particao='complementar_pos_teste',reserva_codificada=True)
    audit.write_json(report/'execucao_encoder.json',enc)
    packer=context.Packer(state['docs'],state['tokenizer']);gold={q['query_id']:q for q in state['gold']}
    curves=[];details=[];parts=[];ranks=[];trunc=[]
    for f in state['config']['finalistas']:
        version=f['versao'];index=version if f['familia']=='fixa' else '_paragrafo_index'
        cap=None if f['familia']=='fixa' else 500
        rows=state['units'][index];matrix=np.stack([vectors[r['texto_sha256']] for r in rows]);lexical=base.BM25(rows)
        for r in rows:trunc.append(dict(indice=index,chunk_id=r['chunk_id'],registro_id=r['registro_id'],**views[r['texto_sha256']]))
        for retriever in ('BGE-M3','BM25'):
            for q in state['questions']:
                checkpoint=report/f"consulta_{version}_{retriever}_{q['query_id']}.json"
                if checkpoint.exists():saved=json.loads(checkpoint.read_text(encoding='utf-8'))
                else:
                    if retriever=='BM25':ranking=lexical.search(q['pergunta'],len(rows))
                    else:
                        scores=matrix@vectors[base.sha(q['pergunta'])]
                        order=sorted(range(len(rows)),key=lambda i:(-float(scores[i]),rows[i]['chunk_id']))
                        ranking=[dict(rows[i],rank=j+1,score=float(scores[i])) for j,i in enumerate(order)]
                    common=dict(query_id=q['query_id'],versao=version,recuperador=retriever,coorte=cohort(q['query_id'],state['config']))
                    g=gold.get(q['query_id']);eligible=g is not None and g.get('avaliacao','suporte_intervalos')=='suporte_intervalos'
                    saved=dict(curves=[],details=[],parts=[],ranking=[dict(common,**{k:r[k] for k in ('chunk_id','registro_id','rank','score','inicio','fim')}) for r in ranking[:10]])
                    for budget in adv.BUDGETS:
                        selected,used,cuts,examined=packer.pack(ranking,budget,window_tokens=cap)
                        saved['curves'].append(dict(common,orcamento=budget,cobertura=adv.support_fraction(g,selected) if eligible else None,
                            tokens_utilizados=used,cortes=cuts,examinadas=examined,unidades_distintas=len({r['chunk_id'] for r in selected}),
                            estado='avaliada_com_intervalos' if eligible else ('comportamental_sem_llm' if g else 'sem_gabarito_intervalos')))
                        saved['parts'].extend(dict(common,orcamento=budget,**{k:r[k] for k in ('chunk_id','registro_id','rank','inicio','fim')}) for r in selected)
                        if budget==2500 and eligible:
                            d=experiment._diagnosis(g,ranking,selected,rows,views,{},version,retriever,budget,used,cuts)
                            d.update(coorte=common['coorte'],primeiro_rank_evidencia=next((r['rank'] for r in ranking if adv.support_fraction(g,[r])>0),None))
                            saved['details'].append(d)
                    audit.write_json(checkpoint,saved)
                curves.extend(saved['curves']);details.extend(saved['details']);parts.extend(saved['parts']);ranks.extend(saved['ranking'])
            print('Avaliado:',retriever,version,'30 consultas',flush=True)
    frame=pd.DataFrame(curves);frame.to_csv(report/'cobertura.csv',index=False)
    pd.DataFrame(parts).to_csv(report/'contextos.csv',index=False);pd.DataFrame(details).to_csv(report/'diagnostico.csv',index=False)
    pd.DataFrame(ranks).to_csv(report/'ranking_top10.csv',index=False);pd.DataFrame(trunc).to_csv(report/'truncamento_encoder.csv',index=False)
    valid=frame[frame.cobertura.notna()&frame.orcamento.eq(2500)]
    summary=valid.groupby(['coorte','recuperador','versao'],as_index=False).agg(cobertura_2500=('cobertura','mean'),perguntas=('query_id','size'),tokens_medios=('tokens_utilizados','mean'))
    summary.to_csv(report/'resumo_2500.csv',index=False)
    pairs=compare(frame,state['config']['coorte_primaria']);pairs.to_csv(report/'bootstrap.csv',index=False)
    audit.write_json(report/'concluido.json',dict(status='complementar_concluida',consultas=30,finalistas=2,recuperadores=2,
        gabaritos_com_intervalos=23,perguntas_reserva_com_intervalos=6,corpus_documentos=len(state['docs']),
        protocolo_sha256=audit.hash_file(report/'protocolo_complementar.json')))
    print(summary.to_string(index=False),flush=True)
    return report
