"""Três unidades de recuperação e avaliação por evidência exata, sem inferir mérito por menção."""
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
import re
import time
import unicodedata

import numpy as np
import pandas as pd

from . import audit, chunking, light_nlp, privacy, perguntas_csv

VERSOES = {'janela_500':'Janela fixa — 500 tokens',
           'paragrafo':'Parágrafo do acórdão',
           'secao_tema':'Seção e tema do acórdão'}
SECOES = re.compile(r'(?im)^[ \t]*(?:(?:[IVXLCDM]+|\d+(?:\.\d+)*)[. \t–—-]+)?'
    r'(RELAT[ÓO]RIO|FUNDAMENTA[ÇC][ÃA]O|VOTO|DISPOSITIVO|CONCLUS[ÃA]O|AC[ÓO]RD[ÃA]O)'
    r'[ \t]*[:. \t–—-]*$')
TEMAS = {
    'horas_extras':r'horas? extras?|sobrejornada',
    'admissibilidade':r'admissibilidade|pressupostos? recursa[il]s?|tempestividade|deser[çc][ãa]o|transcend[êe]ncia|prequestionamento',
    'intervalo_intrajornada':r'intervalo intrajornada',
    'adicional_noturno':r'adicional noturno',
    'vinculo_emprego':r'v[íi]nculo (?:de emprego|empregat[íi]cio)',
    'danos_morais':r'danos? mora[il]s?',
    'honorarios':r'honor[áa]rios',
    'prescricao':r'prescri[çc][ãa]o',
    'verbas_rescisorias':r'verbas rescis[óo]rias|aviso.pr[ée]vio',
}
TOKEN = re.compile(r'\w+', re.UNICODE)


def sha(text):return hashlib.sha256(text.encode('utf-8')).hexdigest()


def paragraph_spans(text):
    """Limites de formatação, não numeração oficial inferida do nada."""
    separators=list(re.finditer(r'\n[ \t]*\n+',text))
    method='linhas_em_branco'
    if not separators:
        separators=list(re.finditer(r'\n+',text));method='quebras_simples_fallback'
    if not separators:method='texto_continuo_sem_limite_de_paragrafo'
    spans=[];start=0
    for match in separators:
        end=match.end()
        if text[start:end].strip():spans.append((start,end));start=end
    if text[start:].strip():spans.append((start,len(text)))
    elif spans:spans[-1]=(spans[-1][0],len(text))
    return spans,method


def theme(text):
    found=[name for name,pattern in TEMAS.items() if re.search(pattern,text,re.I)]
    return (found[0],'mencao_lexical_univoca') if len(found)==1 else ('multiplos_temas','ambiguo') if found else ('nao_identificado','sem_sinal')


def section_theme_spans(text):
    paragraphs,paragraph_method=paragraph_spans(text)
    headings=list(SECOES.finditer(text))
    # Respeitar títulos mesmo sem linhas em branco antes/depois deles.
    cuts=sorted({0,len(text)}|{x for pair in paragraphs for x in pair}|{m.start() for m in headings}|{m.end() for m in headings})
    pieces=[];section='nao_identificada';explicit_theme=None
    for a,b in zip(cuts,cuts[1:]):
        fragment=text[a:b]
        heading=SECOES.fullmatch(fragment.strip())
        if heading:
            label=heading.group(1).casefold()
            section='relatorio' if label.startswith('relat') else 'dispositivo' if label in ('dispositivo','conclusão','conclusao','acórdão','acordao') else 'fundamentacao' if label.startswith('fundament') else 'voto'
            explicit_theme=None
        topic,method=theme(fragment)
        stripped=re.sub(r'^(?:[IVXLCDM]+|\d+(?:\.\d+)*)[.\s–—-]+','',fragment.strip(),flags=re.I)
        is_topic_heading=any(re.fullmatch(pattern+r'\s*[:.\s–—-]*',stripped,re.I) for pattern in TEMAS.values())
        if is_topic_heading and topic not in ('multiplos_temas','nao_identificado'):
            explicit_theme=topic;method='titulo_tematico_explicito'
        elif topic=='multiplos_temas' and explicit_theme:
            topic=explicit_theme;method='titulo_tematico_com_multiplas_mencoes_no_corpo'
        elif topic=='nao_identificado' and explicit_theme:
            topic=explicit_theme;method='herdado_do_titulo_tematico'
        elif topic not in ('nao_identificado','multiplos_temas') and explicit_theme and topic!=explicit_theme:
            # Não carregar o tema anterior sobre uma mudança lexical inequívoca.
            explicit_theme=None
        item=dict(inicio=a,fim=b,secao=section,tema=topic,metodo_tema=method,metodo_paragrafo=paragraph_method)
        if pieces and pieces[-1]['secao']==section and (not fragment.strip() or pieces[-1]['tema']==topic):
            pieces[-1]['fim']=b
        else:pieces.append(item)
    # Segmentos só de espaços aderem ao vizinho sem perder caracteres.
    cleaned=[]
    for item in pieces:
        if not text[item['inicio']:item['fim']].strip():
            if cleaned:cleaned[-1]['fim']=item['fim']
            continue
        if not cleaned:item['inicio']=0
        cleaned.append(item)
    return cleaned


def make_chunks(doc,version,tokenizer):
    text=doc['texto']
    if privacy.PY_PATTERN.search(text):raise ValueError('Padrão residual de CPF na entrada; conteúdo não exibido.')
    if version=='janela_500':
        raw=[dict(inicio=a,fim=b,secao='nao_classificada',tema='nao_classificado',metodo_tema='nao_aplicavel',metodo_paragrafo='nao_aplicavel')
             for a,b in chunking.split_spans(text,tokenizer,500,0)]
    elif version=='paragrafo':
        spans,method=paragraph_spans(text)
        raw=[dict(inicio=a,fim=b,secao='nao_classificada',tema='nao_classificado',metodo_tema='nao_aplicavel',metodo_paragrafo=method) for a,b in spans]
    elif version=='secao_tema':raw=section_theme_spans(text)
    else:raise ValueError('Versão desconhecida.')
    rows=[];coverage=0
    for index,item in enumerate(raw):
        a,b=item['inicio'],item['fim'];content=text[a:b]
        if a!=coverage or not content.strip():raise ValueError('Cobertura de chunk inválida.')
        coverage=b
        row=dict(item,chunk_id=sha('|'.join([version,doc['registro_id'],str(a),str(b)])),versao=version,
                 registro_id=doc['registro_id'],arquivo_id=doc['arquivo_id'],tribunal=doc['tribunal'],
                 split_proposto=doc['split_proposto'],grupo_avaliacao=doc['grupo_avaliacao'],
                 campo_texto=doc['texto_principal_campo'],parent_arquivo=doc['parent_arquivo'],parent_sha256=doc['parent_sha256'],
                 ordem=index,texto=content,texto_sha256=sha(content),tokens=chunking.token_count(content,tokenizer),
                 dispositivo_ids=[])
        if version=='janela_500' and row['tokens']>500:raise ValueError('Janela acima de 500 tokens.')
        rows.append(row)
    if coverage!=len(text):raise ValueError('Texto incompleto.')
    if version=='secao_tema':
        decisions=[r for r in rows if r['secao']=='dispositivo' and r['tema'] not in ('nao_identificado','multiplos_temas')]
        for row in rows:
            if row['secao'] in ('fundamentacao','voto') and row['tema'] not in ('nao_identificado','multiplos_temas'):
                matches=[d['chunk_id'] for d in decisions if d['tema']==row['tema']]
                # Mais de uma decisão candidata: preservar a ambiguidade, sem escolher por proximidade.
                if len(matches)==1:row['dispositivo_ids']=matches
    return rows


class BM25:
    """Mesmo recuperador lexical para as três versões; sem rótulos/IDs no índice."""
    def __init__(self,rows,k1=1.2,b=.75):
        self.rows=rows;self.k1=k1;self.b=b;self.postings=defaultdict(list)
        self.lengths=[]
        for i,row in enumerate(rows):
            counts=Counter(TOKEN.findall(unicodedata.normalize('NFC',row['texto']).casefold()))
            self.lengths.append(sum(counts.values()))
            for word,count in counts.items():self.postings[word].append((i,count))
        self.lengths=np.array(self.lengths,dtype=float);self.avg=max(float(self.lengths.mean()),1.)
    def search(self,query,k=5):
        scores=np.zeros(len(self.rows));n=len(self.rows)
        for word in set(TOKEN.findall(unicodedata.normalize('NFC',query).casefold())):
            posting=self.postings.get(word,[])
            if not posting:continue
            idf=math.log(1+(n-len(posting)+.5)/(len(posting)+.5))
            for i,freq in posting:
                scores[i]+=idf*(freq*(self.k1+1))/(freq+self.k1*(1-self.b+self.b*self.lengths[i]/self.avg))
        # Empates independem da ordem do corpus; scores nulos não viram resultados artificiais.
        order=sorted(np.flatnonzero(scores>0),key=lambda i:(-scores[i],self.rows[i]['chunk_id']))[:k]
        return [dict(self.rows[i],score=float(scores[i]),rank=j+1) for j,i in enumerate(order)]


def validate_questions(questions,documents):
    ids=set()
    for q in questions:
        if q['query_id'] in ids or not q['pergunta'].strip():raise ValueError('Pergunta inválida/repetida.')
        ids.add(q['query_id'])
        if not q.get('alternativas_suporte'):raise ValueError('Pergunta sem suporte esperado.')
        for group in q['alternativas_suporte']:
            if not group:raise ValueError('Conjunto de suporte vazio.')
            for ref in group:
                doc=documents.get(ref['registro_id'])
                if doc is None or ref['campo_texto']!=doc['texto_principal_campo']:raise ValueError('Documento/campo de referência ausente.')
                a,b=ref['inicio'],ref['fim']
                if type(a) is not int or type(b) is not int or not 0<=a<b<=len(doc['texto']):raise ValueError('Offsets de referência inválidos.')
                if sha(doc['texto'][a:b])!=ref['texto_sha256']:raise ValueError('Hash do suporte esperado divergente.')
                if ref.get('espaco_offsets','documento_base_protegido')!='documento_base_protegido':
                    raise ValueError('Offsets de texto bruto pré-PLN exigem um mapa explícito; não são offsets do documento-base protegido.')
                if ref.get('texto_base_sha256',sha(doc['texto']))!=sha(doc['texto']):raise ValueError('Documento-base do gabarito alterado.')


def ref_covered(ref,results):
    # A união permite que uma referência atravesse duas janelas sem conceder acerto por 1 caractere.
    spans=sorted((r['inicio'],r['fim']) for r in results if r['registro_id']==ref['registro_id'] and r['campo_texto']==ref['campo_texto'])
    end=ref['inicio']
    for a,b in spans:
        if a>end:break
        if b>end:end=b
        if end>=ref['fim']:return True
    return False


def question_score(question,results):
    from .chunking_avancado import support_fraction
    expected={r['registro_id'] for group in question['alternativas_suporte'] for r in group}
    document_hit=any(r['registro_id'] in expected for r in results)
    support_hit=any(all(ref_covered(ref,results) for ref in group) for group in question['alternativas_suporte'])
    first=next((k for k in range(1,len(results)+1)
                if any(all(ref_covered(ref,results[:k]) for ref in group) for group in question['alternativas_suporte'])),None)
    return dict(query_id=question['query_id'],acerto_documento_5=int(document_hit),
                suporte_fracao=support_fraction(question,results),
                acerto_suporte_5=int(support_hit),documento_sem_suporte_5=int(document_hit and not support_hit),
                mrr_suporte_5=1/first if first else 0.,primeiro_prefixo_com_suporte=first,
                tokens_top5=sum(r['tokens'] for r in results))


def evaluate(rows,questions,documents):
    validate_questions(questions,documents)
    if not questions:return [],[],dict(status='sem_perguntas_com_suporte',perguntas=0,hit_suporte_5=None,hit_documento_5=None)
    backend=BM25(rows);by_id={r['chunk_id']:r for r in rows};scores=[];ranking=[]
    for q in questions:
        results=backend.search(q['pergunta'],5)
        result=question_score(q,results)
        linked={ident for r in results for ident in r['dispositivo_ids']}
        expanded=results+[by_id[ident] for ident in sorted(linked) if ident not in {r['chunk_id'] for r in results}]
        result['acerto_suporte_5_apos_vinculo']=question_score(q,expanded)['acerto_suporte_5']
        result['tokens_apos_vinculo']=sum(r['tokens'] for r in expanded)
        scores.append(result)
        for r in results:
            ranking.append(dict(query_id=q['query_id'],chunk_id=r['chunk_id'],registro_id=r['registro_id'],rank=r['rank'],score=r['score'],
                                inicio=r['inicio'],fim=r['fim'],secao=r['secao'],tema=r['tema'],tokens=r['tokens']))
    frame=pd.DataFrame(scores)
    summary=dict(status='avaliado',perguntas=len(questions),
                 perguntas_com_suporte_top5=int(frame.acerto_suporte_5.sum()),
                 hit_suporte_5=float(frame.acerto_suporte_5.mean()),hit_documento_5=float(frame.acerto_documento_5.mean()),
                 documento_sem_suporte_5=int(frame.documento_sem_suporte_5.sum()),
                 mrr_suporte_5=float(frame.mrr_suporte_5.mean()),tokens_top5_mediana=float(frame.tokens_top5.median()),
                 hit_suporte_5_apos_vinculo=float(frame.acerto_suporte_5_apos_vinculo.mean()))
    return scores,ranking,summary


def controlled_cases():
    """Casos autorais fictícios; nunca constituem jurisprudência ou gabarito real."""
    cases=[('Alfa','horas extras','horas_extras',
            'O recurso não é conhecido por ausência de pressuposto de admissibilidade. Não se examina o mérito do pedido de horas extras.',
            'Não conhecer do recurso quanto às horas extras, sem exame do mérito.'),
           ('Beta','horas extras','horas_extras',
            'Os controles de jornada comprovam a prestação de horas extras sem pagamento. O recurso é provido para deferir o pagamento das horas extras demonstradas.',
            'Dar provimento ao recurso para deferir o pagamento de horas extras.'),
           ('Gama','adicional noturno','adicional_noturno',
            'O recurso sobre adicional noturno é intempestivo. O tribunal não conhece do recurso e não examina a existência do direito ao adicional noturno.',
            'Não conhecer do recurso sobre adicional noturno, por intempestividade.'),
           ('Delta','intervalo intrajornada','intervalo_intrajornada',
            'A prova demonstra a fruição integral do intervalo intrajornada. O tribunal nega provimento ao recurso quanto ao intervalo intrajornada.',
            'Negar provimento ao recurso quanto ao intervalo intrajornada.')]
    docs=[];questions=[]
    for name,subject,topic,reason,decision in cases:
        text=f'CASO FICTÍCIO {name.upper()}\n\nRELATÓRIO\n\n'
        # Distratores narrativos do mesmo documento: acertar o caso não basta.
        for i in range(7):
            text+=f'No caso {name}, o pedido de {subject} foi mencionado pela parte no relatório. A parte requer o pagamento e sustenta seu direito. Este parágrafo {i+1} apenas descreve o pedido; não registra decisão do tribunal.\n\n'
        text+=f'FUNDAMENTAÇÃO\n\n{subject.upper()}\n\n{reason}\n\nDISPOSITIVO\n\n{decision}'
        ident='sintetico_'+name.casefold()
        doc=dict(registro_id=ident,arquivo_id='fixture',tribunal='FICTICIO',texto=text,split_proposto='controle_sintetico',
                 grupo_avaliacao=ident,texto_principal_campo='inteiro_teor',parent_arquivo='casos_sinteticos_autorais',parent_sha256=sha(text))
        refs=[]
        for passage in (reason,decision):
            a=text.index(passage);refs.append([dict(registro_id=ident,campo_texto='inteiro_teor',inicio=a,fim=a+len(passage),texto_sha256=sha(passage))])
        questions.append(dict(query_id='controle_'+name.casefold(),pergunta=f'No caso fictício {name}, o que o tribunal efetivamente decidiu sobre {subject}? Houve exame do mérito ou impedimento de admissibilidade?',
                              origem='sintetica_autoral',alternativas_suporte=refs))
        docs.append(doc)
    return docs,questions


def load_questions(root):
    path=Path(root)/'avaliacao/dados/jurisprudencia/perguntas_suporte.jsonl'
    if not path.exists():return []
    questions=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    for q in questions:
        if q.get('origem')!='jurisprudencia_real':raise ValueError('Perguntas reais e controles devem permanecer separados.')
    return questions


def prepare(root,max_docs=120):
    from transformers import AutoTokenizer
    root=Path(root).resolve();tokenizer=AutoTokenizer.from_pretrained('BAAI/bge-m3',local_files_only=True,use_fast=True)
    sampled,review,pln=chunking.select_sample(root,max_docs)
    docs=[r for r in sampled if r['texto_principal_campo']=='inteiro_teor']
    questions=load_questions(root)
    queries,query_manifest=perguntas_csv.load(root)
    if queries:
        supplied={q['query_id']:q for q in queries}
        for q in questions:
            if q['query_id'] not in supplied or q['pergunta']!=supplied[q['query_id']]['pergunta']:
                raise ValueError('Gabarito não corresponde ao conjunto CSV ativo.')
    wanted={ref['registro_id'] for q in questions for group in q['alternativas_suporte'] for ref in group}-{r['registro_id'] for r in docs}
    if wanted:
        # Inclui os documentos esperados e mantém os demais como distratores; não filtra a busca pelo gabarito.
        import pyarrow.parquet as pq
        idx=pq.read_table(root/review['indice'],filters=[('registro_id','in',sorted(wanted))]).to_pylist()
        metadata={r['registro_id']:r for r in idx}
        for f in pln['arquivos']:
            ids=[i for i,m in metadata.items() if m['arquivo_id']==f['arquivo_id']]
            if not ids:continue
            p=root/f['arquivo']
            if audit.hash_file(p)!=f['sha256']:raise ValueError('Shard de referência alterado.')
            for r in pq.read_table(p,filters=[('registro_id','in',ids)]).to_pylist():
                if r['texto_principal_campo']!='inteiro_teor':raise ValueError('Pergunta de acórdão aponta para campo diferente da íntegra declarada.')
                m=metadata.pop(r['registro_id']);wanted.remove(r['registro_id'])
                r.update(texto=r['inteiro_teor'],parent_arquivo=f['arquivo'],parent_sha256=f['sha256'],
                         split_proposto=m['split_proposto'],grupo_avaliacao=m['grupo_avaliacao'])
                docs.append(r)
        if wanted:raise ValueError('Referências fora da base protegida ativa.')
    documents={d['registro_id']:d for d in docs};validate_questions(questions,documents)
    fixtures,controls=controlled_cases()
    config=dict(versao=2,max_documentos_amostra=max_docs,documentos_ids=sorted(documents),
                indice_sha256=review['indice_sha256'],base_pln_csv_sha256=pln['csv_sha256'],
                perguntas_sha256=sha(json.dumps(questions,sort_keys=True,ensure_ascii=False)),
                codigo_sha256=audit.hash_file(__file__),versoes=VERSOES,k=5,
                recuperador=dict(nome='BM25 lexical',k1=1.2,b=.75,normalizacao='NFC e casefold apenas para o índice'),
                tokenizador='BAAI/bge-m3',sobreposicao_janela_tokens=0,
                unidade_suporte='Intervalos exatos sobre texto protegido; um conjunto alternativo deve estar integralmente coberto pelo top 5.',
                fonte_coliee='https://coliee.org/COLIEE2025/tasks/task2')
    config['perguntas_legislacao_permitidas']=False
    config['csv_perguntas_sha256']=query_manifest['original_sha256'] if query_manifest else None
    config['perguntas_fornecidas']=len(queries)
    config['codigo_leitura_csv_sha256']=audit.hash_file(perguntas_csv.__file__)
    identity=sha(json.dumps(config,sort_keys=True,ensure_ascii=False))
    data=root/'dados/chunks/jurisprudencia/suporte'/identity;report=root/'dados/relatorios/jurisprudencia/chunking_suporte'/identity
    data.mkdir(parents=True,exist_ok=True);report.mkdir(parents=True,exist_ok=True)
    audit.write_json(report/'configuracao.json',config)
    return dict(root=root,tokenizer=tokenizer,docs=docs,questions=questions,queries=queries,query_manifest=query_manifest,fixtures=fixtures,controls=controls,
                data=data,report=report,config=config,identity=identity,results=[],chunks={})


def experiment(state,version):
    import pyarrow as pa
    import pyarrow.parquet as pq
    start=time.perf_counter();real=[];controlled=[]
    builder=state.get('chunk_builder',make_chunks)
    for doc in state['docs']:real.extend(builder(doc,version,state['tokenizer']))
    for doc in state['fixtures']:controlled.extend(builder(doc,version,state['tokenizer']))
    if len({r['chunk_id'] for r in real})!=len(real):raise ValueError('ID repetido.')
    target=state['data']/(version+'.parquet');pq.write_table(pa.Table.from_pylist(real),target,compression='zstd')
    # Releitura de texto/offset e referências do dispositivo após a exportação.
    exported=pq.read_table(target).to_pylist();documents={r['registro_id']:r for r in state['docs']}
    valid_ids={r['chunk_id'] for r in exported}
    if len(exported)!=len(real):raise ValueError('Contagem divergente na exportação.')
    for r in exported:
        if documents[r['registro_id']]['texto'][r['inicio']:r['fim']]!=r['texto'] or sha(r['texto'])!=r['texto_sha256']:raise ValueError('Exportação sem fidelidade ao texto protegido.')
        if any(i not in valid_ids for i in r['dispositivo_ids']):raise ValueError('Ligação ao dispositivo inexistente.')
    scores,ranks,metrics=evaluate(real,state['questions'],documents)
    supplied_ranks=[];supplied_searches=[]
    if state['queries']:
        searcher=BM25(real)
        annotated={q['query_id'] for q in state['questions']}
        for q in state['queries']:
            top=searcher.search(q['pergunta'],5)
            supplied_searches.append(dict(query_id=q['query_id'],tema=q['tema'],tipo=q['tipo'],dificuldade=q['dificuldade'],
                resultados=len(top),documentos_distintos=len({r['registro_id'] for r in top}),tokens_top5=sum(r['tokens'] for r in top),
                suporte_anotado=q['query_id'] in annotated,
                status='com_referencia_de_suporte' if q['query_id'] in annotated else 'busca_executada_sem_gabarito_de_suporte'))
            for r in top:
                supplied_ranks.append(dict(query_id=q['query_id'],chunk_id=r['chunk_id'],registro_id=r['registro_id'],rank=r['rank'],score=r['score'],
                    campo_texto=r['campo_texto'],inicio=r['inicio'],fim=r['fim'],texto_sha256=r['texto_sha256'],secao=r['secao'],tema=r['tema'],tokens=r['tokens']))
    audit.write_json(state['report']/(version+'_buscas_csv.json'),supplied_searches)
    audit.write_json(state['report']/(version+'_ranking_csv.json'),supplied_ranks)
    annotated_ids={q['query_id'] for q in state['questions']}
    metrics.update(perguntas_fornecidas=len(state['queries']),perguntas_sem_suporte_anotado=sum(q['query_id'] not in annotated_ids for q in state['queries']))
    c_scores,c_ranks,c_metrics=evaluate(controlled,state['controls'],{r['registro_id']:r for r in state['fixtures']})
    for name,values in [('perguntas_reais',scores),('ranking_real',ranks),('controle_sintetico',c_scores),('ranking_sintetico',c_ranks)]:
        audit.write_json(state['report']/(version+'_'+name+'.json'),values)
    frame=pd.DataFrame(real)
    stats=dict(versao=version,titulo=state.get('titles',VERSOES)[version],documentos=len(documents),chunks=len(real),
               tokens_mediana=float(frame.tokens.median()),tokens_p95=float(frame.tokens.quantile(.95)),tokens_maximo=int(frame.tokens.max()),
               chunks_acima_500_tokens=int(frame.tokens.gt(500).sum()),
               chunks_com_vinculo_dispositivo=int(frame.dispositivo_ids.map(bool).sum()),
               cobertura_caracteres_pct=100.,segundos=time.perf_counter()-start,
               consultas_csv_executadas=len(supplied_searches),resultados_csv_recuperados=len(supplied_ranks),
               tokens_top5_csv_mediana=float(np.median([r['tokens_top5'] for r in supplied_searches])) if supplied_searches else None,
               parquet=str(target.relative_to(state['root'])),parquet_sha256=audit.hash_file(target),
               metricas_reais=metrics,metricas_controle_sintetico=c_metrics)
    audit.write_json(state['report']/(version+'.json'),stats)
    state['results'].append(stats);state['chunks'][version]=real
    return frame.drop(columns=['texto']),stats,pd.DataFrame(c_scores)


def plot_version(state,frame,version):
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(11,3.7))
    axes[0].hist(frame.tokens,bins=30,color='#287b8e',edgecolor='white')
    axes[0].set(xlabel='Tokens BGE-M3 por unidade',ylabel='Quantidade',title='Tamanho dos trechos reais')
    axes[0].axvline(500,color='#b23b43',linestyle='--',label='Referência de 500 tokens');axes[0].legend(fontsize=8)
    if state['queries']:
        searches=json.loads((state['report']/(version+'_buscas_csv.json')).read_text(encoding='utf-8'))
        axes[1].hist([r['tokens_top5'] for r in searches],bins=12,color='#c58a34',edgecolor='white')
        axes[1].set(xlabel='Tokens recuperados no top 5',ylabel='Perguntas do CSV',title=f"{len(searches)} consultas reais — custo do contexto")
    else:
        scores=json.loads((state['report']/(version+'_controle_sintetico.json')).read_text(encoding='utf-8'))
        axes[1].bar(['Documento@5','Suporte@5'],[np.mean([r['acerto_documento_5'] for r in scores]),np.mean([r['acerto_suporte_5'] for r in scores])],color=['#c58a34','#287b8e'])
        axes[1].set(ylim=(0,1.1),ylabel='Proporção de perguntas',title='Controle fictício — não é métrica real')
    fig.suptitle(state.get('titles',VERSOES)[version]);fig.tight_layout();fig.savefig(state['report']/(version+'.png'),dpi=140);plt.show()


def finish(state):
    import matplotlib.pyplot as plt
    if len(state['results'])!=3:raise ValueError('Comparação incompleta.')
    # Mesmo corpus de documentos, sem dar crédito a metadados como se fossem evidência.
    ids=[{r['registro_id'] for r in state['chunks'][v]} for v in VERSOES]
    if not ids[0]==ids[1]==ids[2]:raise ValueError('Corpora diferentes entre versões.')
    metrics=[]
    for result in state['results']:
        for scope,key in [('jurisprudencia_real','metricas_reais'),('controle_sintetico','metricas_controle_sintetico')]:
            metrics.append(dict(versao=result['versao'],escopo=scope,**result[key]))
    frame=pd.DataFrame(metrics);frame.to_csv(state['report']/'comparacao_metricas.csv',index=False,encoding='utf-8-sig')
    fig,axes=plt.subplots(1,2,figsize=(12,4))
    control=frame[frame.escopo.eq('controle_sintetico')]
    x=np.arange(3)
    axes[0].bar(x-.18,control.hit_documento_5,.36,label='Documento@5',color='#c58a34')
    axes[0].bar(x+.18,control.hit_suporte_5,.36,label='Suporte@5',color='#287b8e')
    axes[0].set_xticks(x,list(VERSOES),rotation=15);axes[0].set(ylim=(0,1.1),title='Controle fictício: documento × suporte');axes[0].legend()
    if state['questions']:
        real=frame[frame.escopo.eq('jurisprudencia_real')]
        axes[1].bar(real.versao,real.hit_suporte_5,color='#287b8e');axes[1].set(ylim=(0,1.1),title='Perguntas reais — Suporte@5')
    else:
        axes[1].axis('off');axes[1].text(.5,.5,f"{len(state['queries'])} perguntas do CSV consultadas\n\nMétrica de suporte ainda não mensurável:\nnão há trechos esperados vinculados aos acórdãos.\nAusência de gabarito não significa 0% de acerto.",ha='center',va='center')
    fig.tight_layout();fig.savefig(state['report']/'comparacao_suporte.png',dpi=140);plt.show()
    summary=dict(executado_em_utc=datetime.now(timezone.utc).isoformat(),configuracao=state['config'],resultados=state['results'],
                 perguntas_reais=len(state['questions']),perguntas_controle=len(state['controls']),
                 perguntas_csv_fornecidas=len(state['queries']),
                 estrategia_vencedora_real=None,escopo='Corpus amostral; BM25 lexical; controles autorais separados de jurisprudência real.',
                 limite='Hit de suporte confere referências anotadas por offsets; não é prova automática de entailment nem avaliação de respostas.')
    audit.write_json(state['report']/'resumo.json',summary)
    audit.write_json(state['root']/'dados/relatorios/jurisprudencia/chunking_suporte/ativa.json',dict(pasta_relatorios=str(state['report'].relative_to(state['root'])),pasta_dados=str(state['data'].relative_to(state['root']))))
    return frame
