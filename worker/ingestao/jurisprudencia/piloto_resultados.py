"""Consolida e apresenta somente resultados concluídos do piloto versionado."""
from pathlib import Path
import hashlib,json,sqlite3
import numpy as np
import pandas as pd
from . import audit,chunking_avancado as adv,chunking_suporte as base,perguntas_csv,piloto_bge

def finalize(root):
    root=Path(root);pointer=json.loads((root/'dados/relatorios/jurisprudencia/piloto_bge/ativa.json').read_text(encoding='utf-8'))
    report=root/pointer['pasta_relatorios'];data=root/pointer['pasta_dados']
    config=json.loads((report/'configuracao.json').read_text(encoding='utf-8'))
    gold_snapshot=report/'gabarito_snapshot.jsonl'
    assert config['gabarito_sha256']==audit.hash_file(gold_snapshot if gold_snapshot.exists() else root/'avaliacao/dados/jurisprudencia/perguntas_suporte.jsonl')
    manifest=json.loads((report/'manifesto_corpus.json').read_text());assert audit.hash_file(root/manifest['arquivo'])==manifest['sha256']
    queries,_=perguntas_csv.load(root);held=piloto_bge.freeze_guard(root,queries)
    assert not held.intersection(config['perguntas_avaliadas']) and config['teste_final_executado'] is False
    import pyarrow.parquet as pq
    docs={d['registro_id']:d for d in pq.read_table(data/'documentos_base.parquet').to_pylist()}
    golden=([json.loads(line) for line in gold_snapshot.read_text(encoding='utf-8').splitlines() if line.strip()]
            if gold_snapshot.exists() else base.load_questions(root))
    base.validate_questions(golden,{i:dict(d,texto_principal_campo=d['campo_texto']) for i,d in docs.items()})
    # Exporta hashes dos vetores efetivos, sem depender da mutabilidade do cache compartilhado.
    keys=set()
    for version in adv.TITLES:
        keys.update(pq.read_table(data/(version+'.parquet'),columns=['texto_sha256']).column(0).to_pylist())
    keys.update(base.sha(q['pergunta']) for q in golden)
    db=sqlite3.connect(root/'dados/chunks/jurisprudencia/cache_bge'/(piloto_bge.REVISION+'_float32_8192.sqlite'))
    vectors=[]
    for key in sorted(keys):
        item=db.execute('SELECT vector,view FROM embeddings WHERE hash=?',(key,)).fetchone();assert item is not None
        blob,view=item;v=np.frombuffer(blob,dtype=np.float32);assert v.shape==(1024,) and np.isfinite(v).all() and abs(np.linalg.norm(v)-1)<1e-5
        vectors.append(dict(texto_sha256=key,vetor_sha256=hashlib.sha256(blob).hexdigest(),**json.loads(view)))
    db.close();audit.write_json(report/'manifesto_vetores.json',dict(modelo=piloto_bge.MODEL,revisao=piloto_bge.REVISION,entradas=vectors))
    curves=pd.read_csv(report/'cobertura_por_pergunta.csv');assert (curves.tokens_utilizados<=curves.orcamento).all()
    assert curves.query_id.nunique()==8 and not set(curves.query_id)&held
    assert curves.groupby(['recuperador','versao','orcamento']).size().eq(8).all()
    assert curves.cobertura.between(0,1).all()
    costs=pd.read_csv(report/'custo_apos_expansao.csv');ranking=pd.read_csv(report/'ranking.csv')
    byquery={q['query_id']:q for q in queries};details=[]
    for r in costs.to_dict('records'):
        selected=ranking[(ranking.query_id==r['query_id'])&(ranking.versao==r['versao'])&(ranking.recuperador==r['recuperador'])].sort_values('rank').head(5)
        units=pq.read_table(data/(r['versao']+'.parquet'),filters=[('chunk_id','in',selected.chunk_id.tolist())]).to_pylist()
        rows={u['chunk_id']:u for u in units};ranked=[rows[c] for c in selected.chunk_id]
        # Custo por documento depois da expansão: mesmas regras, sem somar pais repetidos.
        contribution={i:piloto_bge.expanded_cost([u for u in ranked if u['registro_id']==i],docs,
                          _tokenizer())['tokens_contexto_top5_expandido'] for i in selected.registro_id.unique()}
        ident=max(contribution,key=contribution.get)
        q=byquery[r['query_id']]
        details.append(dict(r,tema=q['tema'],alvo_chunking=q['alvo_chunking'],acordao_dominante=ident,
            tokens_documento_dominante=contribution[ident],fundamentacao_longa='long' in q['alvo_chunking'].casefold()))
    pd.DataFrame(details).to_csv(report/'custo_expandido_por_pergunta_documento.csv',index=False)
    primary=pd.read_csv(report/'resumo_2500.csv');best=primary.sort_values('cobertura_media_2500',ascending=False).iloc[0]
    best_dense=primary[primary.recuperador.eq('BGE-M3')].sort_values('cobertura_media_2500',ascending=False).iloc[0]
    best_bm=primary[primary.recuperador.eq('BM25')].sort_values('cobertura_media_2500',ascending=False).iloc[0]
    pair=pd.read_csv(report/'estatistica_pareada.csv');a='BGE-M3 / '+best_dense['versao'];b='BM25 / '+best_bm['versao']
    p=pair[(pair.a==a)&(pair.b==b)]
    if len(p):d=p.iloc[0].to_dict()
    else:
        p=pair[(pair.a==b)&(pair.b==a)]
        if len(p):
            old=p.iloc[0];d=dict(a=a,b=b,n=old.n,vitorias=old.derrotas,empates=old.empates,derrotas=old.vitorias,
                delta_media=-old.delta_media,ic95_inf=-old.ic95_sup,ic95_sup=-old.ic95_inf)
        else:d=None
    conclusion=dict(melhor_observado=best.to_dict(),melhor_bge=best_dense.to_dict(),melhor_bm25=best_bm.to_dict(),comparacao=d,
        limite='Oito perguntas de ajuste, sete documentos de suporte e dois distratores. Amostra enriquecida; não estima a recuperação no corpus integral.',
        significado='Cobertura mede fração dos caracteres da evidência esperada, não taxa de respostas corretas do LLM.',
        regra_decisao='Manter os finalistas para ampliação do ajuste; não declarar superioridade geral por este piloto.',
        teste_final='Sete perguntas reservadas; nenhuma delas foi buscada, anotada ou codificada nesta etapa.')
    audit.write_json(report/'veredicto.json',conclusion)
    _plot_expanded_cost(report)
    (report/'executado_piloto_resultados.py').write_bytes(Path(__file__).read_bytes())
    files=[p for p in report.iterdir() if p.is_file() and p.name!='manifesto_resultados.json']
    audit.write_json(report/'manifesto_resultados.json',dict(arquivos=[dict(arquivo=p.name,sha256=audit.hash_file(p)) for p in sorted(files)]))
    return report,conclusion

def _plot_expanded_cost(report):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    costs=pd.read_csv(report/'custo_apos_expansao.csv')
    out=pd.read_csv(report/'outliers_contexto_expandido.csv')
    fig,axes=plt.subplots(1,2,figsize=(14,6),sharey=True)
    for ax,retriever in zip(axes,('BM25','BGE-M3')):
        groups=[costs[(costs.recuperador==retriever)&(costs.versao==v)] for v in adv.TITLES]
        ax.boxplot([g.tokens_contexto_top5_expandido for g in groups],tick_labels=list(adv.TITLES),showfliers=False)
        for i,(version,g) in enumerate(zip(adv.TITLES,groups),1):
            marked=set(out[(out.recuperador==retriever)&(out.versao==version)].query_id)
            for j,r in enumerate(g.sort_values('query_id').itertuples()):
                x=i+(j-3.5)*.028
                ax.scatter(x,r.tokens_contexto_top5_expandido,s=20,alpha=.7,color='#2c6e9b')
                if r.query_id in marked:
                    label=f"P{int(r.query_id.split('_')[1]):02d}"
                    ax.annotate(label,(x,r.tokens_contexto_top5_expandido),fontsize=8,
                        xytext=(7,8 if j%2 else -12),textcoords='offset points',
                        bbox=dict(facecolor='white',alpha=.85,edgecolor='none',pad=1),
                        arrowprops=dict(arrowstyle='-',color='#555',lw=.5))
        ax.set_yscale('log');ax.set_title(retriever+' — custo após expansão e deduplicação')
        ax.tick_params(axis='x',rotation=45);ax.grid(axis='y',alpha=.2)
    axes[0].set_ylabel('Tokens do contexto top 5, antes do corte por orçamento (log)')
    fig.suptitle('Rótulos identificam outliers; todos os valores entram na mediana, p90 e máximo',fontsize=10)
    fig.tight_layout();fig.savefig(report/'custo_expandido_log.png',dpi=150);plt.close(fig)

_TOK=None
def _tokenizer():
    global _TOK
    if _TOK is None:
        from transformers import AutoTokenizer
        _TOK=AutoTokenizer.from_pretrained('BAAI/bge-m3',revision=piloto_bge.REVISION,local_files_only=True,use_fast=True)
    return _TOK

def render(root):
    from IPython.display import display,Markdown,Image
    root=Path(root);pointer=json.loads((root/'dados/relatorios/jurisprudencia/piloto_bge/ativa.json').read_text())
    report=root/pointer['pasta_relatorios'];v=json.loads((report/'veredicto.json').read_text(encoding='utf-8'))
    config=json.loads((report/'configuracao.json').read_text(encoding='utf-8'))
    gold_snapshot=report/'gabarito_snapshot.jsonl'
    assert config['gabarito_sha256']==audit.hash_file(gold_snapshot if gold_snapshot.exists() else root/'avaliacao/dados/jurisprudencia/perguntas_suporte.jsonl')
    for f in json.loads((report/'manifesto_resultados.json').read_text(encoding='utf-8'))['arquivos']:
        assert audit.hash_file(report/f['arquivo'])==f['sha256']
    display(Markdown('**Cobertura média com orçamento de 2.500 tokens — piloto concluído:**'))
    main=pd.read_csv(report/'resumo_2500.csv');display(main.round(4));display(Image(filename=str(report/'curva_cobertura.png')))
    best=v['melhor_observado'];p=v['comparacao']
    text=f"**Diagnóstico:** o maior valor observado foi **{100*best['cobertura_media_2500']:.1f}%**, com {best['recuperador']} e `{best['versao']}`. "
    if p:
        text+=f"O melhor BGE (`{v['melhor_bge']['versao']}`) contra o melhor BM25 (`{v['melhor_bm25']['versao']}`) teve {int(p['vitorias'])} vitórias, {int(p['empates'])} empates e {int(p['derrotas'])} derrotas; diferença média de {100*p['delta_media']:.1f} pontos percentuais, IC bootstrap pareado de 95% [{100*p['ic95_inf']:.1f}; {100*p['ic95_sup']:.1f}]. "
        if p['ic95_inf']<=0<=p['ic95_sup']:text+='O intervalo inclui zero: o piloto não permite declarar uma vantagem consistente entre esses finalistas. '
    text+=v['significado']+' '+v['limite']+' '+v['teste_final']
    display(Markdown(text))
    curves=pd.read_csv(report/'cobertura_por_pergunta.csv')
    selected=curves[curves.orcamento.eq(2500)&(
        ((curves.recuperador=='BM25')&(curves.versao==v['melhor_bm25']['versao']))|
        ((curves.recuperador=='BGE-M3')&(curves.versao==v['melhor_bge']['versao'])))]
    display(Markdown('**Cobertura por pergunta nos dois finalistas observados:**'))
    matrix=selected.pivot(index='query_id',columns='recuperador',values='cobertura')
    display(matrix.round(4))
    empty=matrix.index[matrix.eq(0).all(axis=1)].tolist()
    if empty:
        display(Markdown('**Falha concreta:** '+', '.join(empty)+' ficaram sem cobertura da evidência esperada nos dois finalistas com 2.500 tokens. Isso impede tratar o maior valor médio como solução suficiente para essas perguntas.'))
    display(Markdown('**Expansão de contexto:** recuperar o parágrafo e anexar a seção inteira pode multiplicar o custo. O orçamento corta essa expansão; um acerto de documento ou um trecho narrativo não se transforma automaticamente em suporte do fundamento e do resultado. A tabela seguinte mede esse custo depois da expansão.'))
    display(Markdown('**Custo do top 5 após expansão e deduplicação, antes do corte por orçamento:**'))
    display(pd.read_csv(report/'custo_expandido_resumo.csv').round(1));display(Image(filename=str(report/'custo_expandido_log.png')))
    display(Markdown('**Perguntas outliers:** Tukey sobre log(1 + tokens), por estratégia e recuperador; os rótulos no gráfico identificam esses pontos. A tabela detalhada liga cada pergunta ao acórdão que mais contribuiu para o custo.'))
    out=pd.read_csv(report/'outliers_contexto_expandido.csv');detail=pd.read_csv(report/'custo_expandido_por_pergunta_documento.csv')
    display(out.merge(detail,on=['query_id','versao','recuperador','tokens_indice_top5','tokens_contexto_top5_expandido','segmentos_expandidos'],how='left'))
    display(Markdown('**Fragmentação, unidades necessárias e perda de evidência no encoder:**'))
    ev=pd.read_csv(report/'evidencia.csv');display(ev.groupby(['recuperador','versao']).agg(
        taxa_fragmentacao=('evidencia_fragmentada','mean'),unidades_minimas_medias=('unidades_necessarias_minimas','mean'),
        perda_media_encoder=('fracao_evidencia_perdida_encoder','mean')).round(4))
    trunc=pd.read_csv(report/'truncamento_real_encoder.csv')
    display(trunc.groupby('versao').agg(unidades=('chunk_id','size'),unidades_truncadas=('truncado','sum'),maximo_tokens_com_especiais=('tokens_com_especiais','max')))
    display(Markdown('O BGE recebeu até 8.192 tokens contando especiais. Zero no piloto significa ausência de truncamento neste recorte; os limites de contexto de 500–5.000 continuam cortando o texto entregue. O controle longo separado verifica um truncamento real e não entra nas médias de jurisprudência.'))
    display(pd.read_csv(report/'auditoria_chunking.csv').drop(columns=['motivo_vetores_gerados']).round(4))
    display(Markdown('**Comparações pareadas em Cobertura@2500:** bootstrap sobre as mesmas oito perguntas, 2.000 réplicas, seed fixa; análises exploratórias, sem correção para múltiplas comparações.'))
    pairs=pd.read_csv(report/'estatistica_pareada.csv');display(pairs[(pairs.a.str.startswith('BGE-M3'))&(pairs.b.str.startswith('BM25'))].round(4))
    return report
