"""Diagnóstico visual do tamanho do top 5; não executa novas buscas nem usa o teste final."""
from pathlib import Path
import json
import math

import numpy as np
import pandas as pd

from . import audit, perguntas_csv

LABELS={'janela_500':'Janela 500','paragrafo':'Parágrafo','secao_tema':'Seção/tema',
        'paragrafo_minimo':'Parágrafo mínimo','secao_teto':'Seção com teto',
        'paragrafo_secao':'Parágrafo + seção'}


def summarize(searches,questions,rankings):
    metadata=pd.DataFrame(questions)
    if metadata.query_id.duplicated().any():raise ValueError('IDs de pergunta repetidos.')
    frame=searches.merge(metadata[['query_id','id','pergunta','tema','alvo_chunking','dificuldade']],
                         on='query_id',how='left',validate='many_to_one',suffixes=('','_csv'))
    if frame.id.isna().any() or frame[['versao','query_id']].duplicated().any():
        raise ValueError('Consultas inconsistentes com o CSV.')
    if frame.tokens_top5.lt(0).any():raise ValueError('Custo negativo inválido.')
    frame['fundamentacao_longa']=frame.alvo_chunking.str.casefold().str.contains('fundamentação longa',regex=False)
    stats=[]
    for version,part in frame.groupby('versao',sort=False):
        values=part.tokens_top5
        q1,q3=values.quantile([.25,.75]);iqr=q3-q1
        low,high=q1-1.5*iqr,q3+1.5*iqr
        frame.loc[part.index,'limite_inferior_iqr']=low
        frame.loc[part.index,'limite_superior_iqr']=high
        stats.append(dict(versao=version,perguntas=len(values),mediana_tokens=float(values.median()),
            p90_tokens=float(values.quantile(.9)),maximo_tokens=int(values.max()),zero_tokens=int(values.eq(0).sum()),
            q1_tokens=float(q1),q3_tokens=float(q3),iqr_tokens=float(iqr),
            limite_inferior_iqr=float(low),limite_superior_iqr=float(high),
            outliers_altos=int(values.gt(high).sum()),outliers_baixos=int(values.lt(low).sum())))
    frame['tipo_outlier']=np.select([frame.tokens_top5.gt(frame.limite_superior_iqr),frame.tokens_top5.lt(frame.limite_inferior_iqr)],
                                    ['alto','baixo'],default='regular')
    frame['rotulo_pergunta']='P'+frame.id.astype(str).str.zfill(2)
    outliers=frame[frame.tipo_outlier.ne('regular')].copy()
    ranking=pd.DataFrame(rankings)
    documents=pd.DataFrame()
    if ranking.empty and frame.tokens_top5.gt(0).any():raise ValueError('Consulta com tokens sem ranking correspondente.')
    if not ranking.empty:
        if ranking[['versao','query_id','rank']].duplicated().any():raise ValueError('Ranks repetidos.')
        # A soma deve reproduzir exatamente a medida usada pela caixa.
        totals=ranking.groupby(['versao','query_id']).tokens.sum()
        actual=frame.set_index(['versao','query_id']).tokens_top5
        if not totals.reindex(actual.index,fill_value=0).eq(actual).all():raise ValueError('Tokens do ranking não conferem com a consulta.')
        linked=ranking.merge(outliers[['versao','query_id','tipo_outlier','fundamentacao_longa']],
                             on=['versao','query_id'],how='inner',validate='many_to_one')
        if not linked.empty:
            contributions=linked.groupby(['versao','query_id','registro_id'],as_index=False).agg(
                tokens_acordao=('tokens','sum'),maior_chunk_tokens=('tokens','max'),chunks_no_top5=('rank','size'),
                tribunal=('tribunal','first'),arquivo_id=('arquivo_id','first'))
            dominant=contributions.sort_values(['tokens_acordao','registro_id'],ascending=[False,True]).drop_duplicates(['versao','query_id'])
            dominant=dominant.rename(columns={'registro_id':'acordao_dominante','tokens_acordao':'tokens_acordao_dominante'})
            outliers=outliers.merge(dominant,on=['versao','query_id'],how='left',validate='one_to_one')
            outliers['fracao_tokens_acordao_dominante']=outliers.tokens_acordao_dominante/outliers.tokens_top5.replace(0,np.nan)
            documents=linked.groupby('registro_id',as_index=False).agg(
                perguntas_outlier_associadas=('query_id','nunique'),ocorrencias_estrategia_pergunta=('query_id','size'),
                maior_chunk_tokens=('tokens','max'),tribunal=('tribunal','first'),arquivo_id=('arquivo_id','first'))
            # Contagem por par estratégia/pergunta; múltiplos chunks do mesmo acórdão não inflam a frequência.
            pairs=linked.drop_duplicates(['registro_id','versao','query_id']).groupby('registro_id').size()
            documents['ocorrencias_estrategia_pergunta']=documents.registro_id.map(pairs)
            overall=ranking.groupby('registro_id').query_id.nunique()
            documents['perguntas_em_que_aparece_no_top5']=documents.registro_id.map(overall)
            documents['fracao_perguntas_associadas_a_outlier']=documents.perguntas_outlier_associadas/documents.perguntas_em_que_aparece_no_top5
            documents=documents.sort_values(['perguntas_outlier_associadas','maior_chunk_tokens'],ascending=False)
    long_targets=frame.groupby(['versao','fundamentacao_longa'],as_index=False).agg(
        perguntas=('query_id','size'),outliers=('tipo_outlier',lambda x:x.ne('regular').sum()),
        outliers_altos=('tipo_outlier',lambda x:x.eq('alto').sum()),outliers_baixos=('tipo_outlier',lambda x:x.eq('baixo').sum()),
        mediana_tokens=('tokens_top5','median'),maximo_tokens=('tokens_top5','max'))
    long_targets['fracao_outliers']=long_targets.outliers/long_targets.perguntas
    return pd.DataFrame(stats),outliers.sort_values(['versao','tokens_top5'],ascending=[True,False]),documents,long_targets,frame


def render(root,report):
    import matplotlib.pyplot as plt
    from matplotlib.ticker import LogLocator,FuncFormatter
    root=Path(root).resolve();report=Path(report).resolve()
    if not report.is_relative_to(root/'dados/relatorios/jurisprudencia/chunking_avancado'):raise ValueError('Pasta de relatório inválida.')
    summary=json.loads((report/'resumo.json').read_text(encoding='utf-8'))
    queries,manifest=perguntas_csv.load(root)
    if manifest['original_sha256']!=summary['configuracao']['csv_perguntas_sha256']:raise ValueError('CSV diferente da execução.')
    searches=[];rankings=[];sources={}
    for result in summary['resultados']:
        version=result['versao']
        p=report/(version+'_buscas_csv.json');r=report/(version+'_ranking_csv.json')
        sources[p.name]=audit.hash_file(p);sources[r.name]=audit.hash_file(r)
        searches.extend(dict(row,versao=version) for row in json.loads(p.read_text(encoding='utf-8')))
        # Apenas metadados dos chunks: nunca ler texto jurídico para montar este diagnóstico.
        import pyarrow.parquet as pq
        shard=root/result['parquet']
        if audit.hash_file(shard)!=result['parquet_sha256']:raise ValueError('Chunks alterados desde a execução.')
        meta={m['chunk_id']:m for m in pq.read_table(shard,columns=['chunk_id','tribunal','arquivo_id']).to_pylist()}
        for row in json.loads(r.read_text(encoding='utf-8')):
            m=meta[row['chunk_id']]
            rankings.append(dict(row,versao=version,tribunal=m['tribunal'],arquivo_id=m['arquivo_id']))
    stats,outliers,documents,targets,frame=summarize(pd.DataFrame(searches),queries,rankings)
    allowed={r['query_id'] for r in summary['configuracao']['divisao_perguntas'] if r['particao']==summary['particao_executada']}
    if set(frame.query_id)!=allowed:raise ValueError('Diagnóstico inclui perguntas fora da partição executada.')
    order=[r['versao'] for r in summary['resultados']]
    positive=frame[frame.tokens_top5.gt(0)]
    fig,ax=plt.subplots(figsize=(15,6))
    values=[positive.loc[positive.versao.eq(v),'tokens_top5'].to_numpy() for v in order]
    ax.boxplot(values,tick_labels=[LABELS.get(v,v) for v in order],showfliers=False)
    ax.set_yscale('log');ax.yaxis.set_major_locator(LogLocator(base=10,subs=(1,2,5)))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v,p:f'{v:,.0f}'.replace(',','.')))
    ax.set(title=f"Top 5 — {len(allowed)} perguntas de {summary['particao_executada']} (escala logarítmica)",
           ylabel='Soma dos tokens das unidades recuperadas')
    ax.grid(axis='y',which='both',alpha=.2);max_label=positive.tokens_top5.max() if not positive.empty else 1
    for x,version in enumerate(order,1):
        subset=outliers[outliers.versao.eq(version)&outliers.tokens_top5.gt(0)]
        previous=-np.inf
        for value,group in subset.groupby('tokens_top5',sort=True):
            color='#b23b43' if group.tipo_outlier.eq('alto').any() else '#2c68a0'
            ax.scatter([x]*len(group),[value]*len(group),color=color,s=28,zorder=4)
            labels=sorted(group.rotulo_pergunta.tolist())
            label='\n'.join(', '.join(labels[i:i+4]) for i in range(0,len(labels),4))
            ylog=max(math.log10(value),previous+.09);previous=ylog+.07*(label.count('\n'))
            text_y=10**ylog;max_label=max(max_label,text_y)
            ax.annotate(label,xy=(x,value),xytext=(x+.12,text_y),fontsize=8,color=color,
                        ha='left',va='center',arrowprops=dict(arrowstyle='-',color=color,lw=.6))
    if not positive.empty:ax.set_ylim(positive.tokens_top5.min()*.7,max_label*1.4)
    ax.set_xlim(.5,len(order)+.8)
    ax.tick_params(axis='x',rotation=12)
    fig.text(.02,.015,'Pxx = ID da pergunta no CSV. Outliers: abaixo de Q1 − 1,5×IQR (azul) ou acima de Q3 + 1,5×IQR (vermelho), na escala original.\n'
             'Medida do top 5 antes de expansão/corte e sem separadores. Valores zero ficam na tabela, fora do eixo logarítmico.',fontsize=8)
    fig.tight_layout(rect=(0,.075,1,1));fig.savefig(report/'consultas_csv_contexto.png',dpi=150);plt.show()
    for name,data in [('resumo_contexto_mediana_p90_maximo',stats),('perguntas_outliers_contexto',outliers),
                      ('acordaos_associados_outliers',documents),('alvos_fundamentacao_longa_outliers',targets)]:
        audit.write_json(report/(name+'.json'),json.loads(data.to_json(orient='records',force_ascii=False)))
    audit.write_json(report/'proveniencia_grafico_contexto.json',dict(codigo_sha256=audit.hash_file(__file__),
        csv_original_sha256=manifest['original_sha256'],fontes=sources,particao=summary['particao_executada'],
        criterio_outlier='Tukey 1,5 IQR sobre tokens lineares, por estratégia; comparação estrita.',
        perguntas_distintas_outlier=int(outliers.query_id.nunique()),ocorrencias_outlier=len(outliers),
        observacao='Associação com perguntas/acórdãos não prova causa nem relevância jurídica. Nenhuma consulta foi reexecutada.'))
    return stats,outliers,documents,targets
