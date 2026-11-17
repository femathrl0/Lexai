"""Cobertura por orçamento e métricas estruturais da evidência; sem LLM."""
from collections import defaultdict
import pandas as pd


def _merged_gold(group):
    from .chunking_avancado import merge_ranges
    by_source=defaultdict(list)
    for ref in group:by_source[(ref['registro_id'],ref['campo_texto'])].append((ref['inicio'],ref['fim']))
    return [(ident,field,a,b) for (ident,field),spans in by_source.items() for a,b in merge_ranges(spans)]


def _minimum_cover(intervals,units):
    """Cobertura mínima por intervalos em uma dimensão; uma unidade não é contada duas vezes."""
    chosen=set();last_end=-1
    for start,end in intervals:
        point=max(start,last_end)
        while point<end:
            candidates=[r for r in units if r['inicio']<=point<r['fim']]
            if not candidates:return None
            best=max(candidates,key=lambda r:(r['fim'],r['chunk_id']))
            chosen.add(best['chunk_id']);last_end=best['fim'];point=last_end
    return chosen


def evidence_units(question,units,ranking=()):
    """Distingue fragmentar UM intervalo de precisar de várias evidências separadas."""
    from .chunking_avancado import support_fraction
    alternatives=[]
    for index,group in enumerate(question['alternativas_suporte']):
        gold=_merged_gold(group);by_source=defaultdict(list)
        for ident,field,a,b in gold:by_source[(ident,field)].append((a,b))
        chosen=set();fragmented=0;valid=True
        for (ident,field),intervals in by_source.items():
            relevant=[r for r in units if r['registro_id']==ident and r['campo_texto']==field]
            cover=_minimum_cover(intervals,relevant)
            if cover is None:valid=False;break
            chosen.update(cover)
            fragmented+=sum(not any(r['inicio']<=a and b<=r['fim'] for r in relevant) for a,b in intervals)
        if valid:alternatives.append(dict(alternativa=index,unidades_necessarias_minimas=len(chosen),
            intervalos_evidencia=len(gold),intervalos_fragmentados=fragmented,
            evidencia_fragmentada=fragmented>0))
    if not alternatives:
        return dict(alternativa=None,unidades_necessarias_minimas=None,intervalos_evidencia=None,
                    intervalos_fragmentados=None,evidencia_fragmentada=None,unidades_ranqueadas_ate_cobrir=None)
    # Alternativas equivalentes: usar a que demanda menos unidades; desempate por menor fragmentação.
    result=min(alternatives,key=lambda x:(x['unidades_necessarias_minimas'],x['intervalos_fragmentados'],x['alternativa']))
    unique=[];seen=set();prefix=None
    for row in ranking:
        if row['chunk_id'] in seen:continue
        seen.add(row['chunk_id']);unique.append(row)
        if support_fraction(question,unique)>=1-1e-12:prefix=len(unique);break
    result['unidades_ranqueadas_ate_cobrir']=prefix
    return result


def truncation_rates(question,units,tokenizer,limits=(512,8192)):
    from .chunking_avancado import support_fraction,prefix_for_encoder
    docs={r['registro_id'] for g in question['alternativas_suporte'] for r in g}
    relevant=[r for r in units if r['registro_id'] in docs]
    before=support_fraction(question,relevant)
    result=dict(taxa_truncamento_encoder_real=None,estado_encoder='nao_executado_bm25')
    extra=tokenizer.num_special_tokens_to_add(pair=False) if hasattr(tokenizer,'num_special_tokens_to_add') else 0
    for limit in limits:
        retained=[r if r['tokens']+extra<=limit else prefix_for_encoder(r,tokenizer,limit) for r in relevant]
        after=support_fraction(question,retained);loss=max(0.,before-after)
        result[f'evidencia_perdida_encoder_{limit}_simulado']=loss
        result[f'evidencia_truncada_encoder_{limit}_simulado']=loss>1e-12
    return result


def aggregate_evidence(records):
    frame=pd.DataFrame(records);rows=[]
    for (scope,version),group in frame.groupby(['escopo','versao'],sort=False):
        eligible=group[group.unidades_necessarias_minimas.notna()]
        n=len(eligible)
        result=dict(escopo=scope,versao=version,perguntas_total=len(group),perguntas_com_gabarito=n,
            taxa_fragmentacao=float(eligible.evidencia_fragmentada.astype(float).mean()) if n else None,
            media_unidades_necessarias=float(eligible.unidades_necessarias_minimas.mean()) if n else None,
            maximo_unidades_necessarias=int(eligible.unidades_necessarias_minimas.max()) if n else None,
            media_unidades_ranqueadas_ate_cobrir=float(eligible.unidades_ranqueadas_ate_cobrir.mean()) if n and eligible.unidades_ranqueadas_ate_cobrir.notna().any() else None,
            perguntas_sem_cobertura_no_ranking=int(eligible.unidades_ranqueadas_ate_cobrir.isna().sum()) if n else None,
            taxa_truncamento_encoder_real=None,estado_encoder='nao_executado_bm25')
        for limit in (512,8192):
            key=f'evidencia_truncada_encoder_{limit}_simulado'
            result[f'taxa_truncamento_encoder_{limit}_simulada']=float(eligible[key].astype(float).mean()) if n else None
            result[f'fracao_media_evidencia_perdida_encoder_{limit}_simulada']=float(eligible[f'evidencia_perdida_encoder_{limit}_simulado'].mean()) if n else None
        rows.append(result)
    return pd.DataFrame(rows)


def summarize_2500(curves):
    selected=curves[curves.orcamento.eq(2500)]
    result=selected.groupby(['escopo','versao'],as_index=False,sort=False).agg(
        perguntas_total=('query_id','size'),perguntas_com_gabarito=('suporte_fracao','count'),
        cobertura_media_2500=('suporte_fracao','mean'),tokens_utilizados_medios=('tokens_utilizados','mean'))
    result['metrica']='Cobertura@2500';result['orcamento']=2500
    result['estado']=result.perguntas_com_gabarito.map(lambda n:'avaliado' if n else 'sem_gabarito')
    return result


def long_section_demo(tokenizer):
    """Demonstra que um primeiro trecho enorme não pode furar nem ser pulado pelo budget."""
    from . import chunking_avancado as adv,chunking_suporte as base,chunking
    evidence='Conclusão específica: a questão não foi examinada.'
    text='FUNDAMENTAÇÃO\n\n'+('Contexto geral sem conclusão específica. '*2500)+'\n\n'+evidence
    doc=dict(registro_id='controle_secao_longa',texto=text,arquivo_id='fixture',tribunal='FICTICIO',
        split_proposto='controle',grupo_avaliacao='controle_secao_longa',texto_principal_campo='inteiro_teor',
        parent_arquivo='controle_sintetico_autoral',parent_sha256=base.sha(text))
    question=dict(query_id='controle_secao_longa',pergunta='A questão foi examinada?',alternativas_suporte=[[
        adv.original_reference(doc,text.index(evidence),len(text),'fundamentacao')]])
    rows=[]
    for version in ('secao_tema','paragrafo','paragrafo_secao'):
        units=adv.build_chunks(doc,version,tokenizer);ranking=base.BM25(units).search(question['pergunta'],50)
        assert ranking
        if version=='secao_tema':assert ranking[0]['tokens']>8192
        for budget in adv.BUDGETS:
            context,used,cuts=adv.context_at_budget(ranking,{doc['registro_id']:doc},tokenizer,budget)
            rows.append(dict(versao=version,orcamento=budget,tokens_utilizados=used,
                primeiro_trecho_tokens=ranking[0]['tokens'],cobertura_T=adv.support_fraction(question,context),cortes_contexto=cuts))
    return pd.DataFrame(rows)
