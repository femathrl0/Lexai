"""Gráficos e leitura por pergunta do protocolo atual de contexto centrado."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
from . import audit,experimento_orcamento as exp,chunking_avancado as adv,piloto_bge,perguntas_csv

def locate(root):
    root=Path(root);p=json.loads((root/'dados/relatorios/jurisprudencia/orcamento_centrado/ativa.json').read_text(encoding='utf-8'))
    return root/p['pasta_relatorios'],root/p['pasta_dados']

def finalize(root):
    root=Path(root);report,data=locate(root)
    config=json.loads((report/'configuracao.json').read_text(encoding='utf-8'))
    queries,_=perguntas_csv.load(root);held=piloto_bge.freeze_guard(root,queries)
    assert config['gabarito_sha256']==audit.hash_file(report/'gabarito_snapshot.jsonl')==audit.hash_file(root/'avaliacao/dados/jurisprudencia/perguntas_suporte.jsonl')
    assert not set(config['consultas_executadas'])&held and not config['teste_final_executado']
    curve=pd.read_csv(report/'cobertura.csv');diagnosis=pd.read_csv(report/'diagnostico_por_pergunta.csv')
    assert curve.query_id.nunique()==23 and curve.cobertura.count()==17*13*2*4
    assert (curve.tokens_utilizados<=curve.orcamento).all() and curve.cobertura.dropna().between(0,1).all()
    assert not set(curve.query_id)&held
    encoder=json.loads((report/'execucao_encoder.json').read_text(encoding='utf-8'))
    assert set(encoder['consultas_codificadas'])==set(config['consultas_executadas']) and not encoder['reserva_codificada']
    # Ledger dos vetores de documentos, auditoria ampla e consultas efetivamente utilizados.
    import sqlite3,pyarrow.parquet as pq
    keys=set()
    for index in adv.TITLES:keys.update(pq.read_table(data/(index+'.parquet'),columns=['texto_sha256']).column(0).to_pylist())
    keys.update(pq.read_table(data/'secoes_longas_auditoria_ampla.parquet',columns=['texto_sha256']).column(0).to_pylist())
    keys.update(adv.base.sha(q['pergunta']) for q in queries if q['query_id'] not in held)
    db=sqlite3.connect(root/'dados/chunks/jurisprudencia/cache_bge'/(piloto_bge.REVISION+'_float32_8192.sqlite'))
    ledger=[]
    for key in sorted(keys):
        row=db.execute('SELECT vector,view FROM embeddings WHERE hash=?',(key,)).fetchone();assert row is not None
        vector,view=row;values=np.frombuffer(vector,dtype=np.float32)
        assert values.shape==(1024,) and np.isfinite(values).all() and abs(np.linalg.norm(values)-1)<1e-5
        ledger.append(dict(texto_sha256=key,vetor_sha256=hashlib.sha256(vector).hexdigest(),**json.loads(view)))
    db.close();audit.write_json(report/'manifesto_vetores.json',dict(modelo=piloto_bge.MODEL,revisao=piloto_bge.REVISION,entradas=ledger))
    # Mediana/p90/máximo do custo realmente entregue; não usa soma fixa do top 5 como custo principal.
    cost=curve.groupby(['recuperador','versao','orcamento']).agg(
        tokens_mediana=('tokens_utilizados','median'),tokens_p90=('tokens_utilizados',lambda s:s.quantile(.9)),tokens_max=('tokens_utilizados','max'),
        unidades_mediana=('unidades_distintas','median'),unidades_p90=('unidades_distintas',lambda s:s.quantile(.9)),unidades_max=('unidades_distintas','max')).reset_index()
    cost.to_csv(report/'custo_orcamento_resumo.csv',index=False)
    gold_ids=set(config['perguntas_com_evidencia']);byid={q['query_id']:q for q in queries}
    status=[]
    for qid in config['consultas_executadas']:
        status.append(dict(query_id=qid,pergunta=byid[qid]['pergunta'],
            status='com_intervalos_e_metricas' if qid in gold_ids else 'controle_comportamental_sem_metrica_de_suporte' if qid in ('juris_027','juris_028','juris_029') else 'buscas_executadas_sem_intervalo_anotado'))
    pd.DataFrame(status).to_csv(report/'status_perguntas_ajuste.csv',index=False)
    primary=pd.read_csv(report/'resumo_2500.csv');pairs=pd.read_csv(report/'bootstrap_pareado.csv')
    bm=primary[primary.recuperador.eq('BM25')].sort_values(['cobertura_2500','versao'],ascending=[False,True]).iloc[0]
    dense=primary[primary.recuperador.eq('BGE-M3')].sort_values(['cobertura_2500','versao'],ascending=[False,True]).iloc[0]
    a='BGE-M3 / '+dense['versao'];b='BM25 / '+bm['versao']
    pair=pairs[(pairs.coorte=='ajuste_ampliado')&(pairs.a==a)&(pairs.b==b)]
    if len(pair):comparison=pair.iloc[0].to_dict()
    else:
        r=pairs[(pairs.coorte=='ajuste_ampliado')&(pairs.a==b)&(pairs.b==a)].iloc[0]
        comparison=dict(a=a,b=b,n=int(r.n),vitorias=int(r.derrotas),empates=int(r.empates),derrotas=int(r.vitorias),
            delta_media=float(-r.delta_media),ic95_inf=float(-r.ic95_sup),ic95_sup=float(-r.ic95_inf))
    trunc=pd.read_csv(report/'truncamento_secao_real.csv');ablation=pd.read_csv(report/'ablacao_truncamento_secao.csv')
    notes=dict(melhor_bm25=bm.to_dict(),melhor_bge=dense.to_dict(),comparacao=comparison,
        ressalva='Varridos e comparados no ajuste, não no teste final. Melhores valores observados não provam superioridade geral; bootstrap exploratório sem correção para múltiplas comparações. Perguntas gerais podem admitir outros trechos válidos: a cobertura mede as referências anotadas, não a exaustividade jurídica do corpus.',
        perguntas_buscadas=23,perguntas_com_evidencia=17,reservadas=7,
        secao_truncada_piloto=int(trunc[(trunc.escopo=='piloto_secao_tema')].truncado.sum()),
        secao_truncada_auditoria_ampla=int(trunc[(trunc.escopo=='auditoria_ampla_secoes_longas')].truncado.sum()),
        perguntas_acerto_usa_secao_truncada=int(ablation[ablation.orcamento==2500].evidencia_em_unidades_truncadas.gt(0).sum()),
        perguntas_perdem_cobertura_removendo_secoes_truncadas=int(ablation[ablation.orcamento==2500].delta_remocao.gt(1e-12).sum()),
        perguntas_evidencia_apos_corte=int(ablation[ablation.orcamento==2500].evidencia_entregue_fora_prefixo_encoder.gt(1e-12).sum()))
    audit.write_json(report/'veredicto.json',notes)
    plot(report)
    (report/'executado_relatorio_orcamento.py').write_bytes(Path(__file__).read_bytes())
    files=[p for p in report.iterdir() if p.is_file() and p.name!='manifesto_resultados.json']
    audit.write_json(report/'manifesto_resultados.json',dict(arquivos=[dict(arquivo=p.name,sha256=audit.hash_file(p)) for p in sorted(files)]))
    return report,notes

def plot(report):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    curve=pd.read_csv(report/'cobertura.csv').dropna(subset=['cobertura']);primary=pd.read_csv(report/'resumo_2500.csv')
    fig,axes=plt.subplots(1,2,figsize=(15,5),sharey=True)
    for ax,retriever in zip(axes,('BM25','BGE-M3')):
        windows=primary[(primary.recuperador==retriever)&primary.versao.str.startswith('paragrafo_janela_')]
        best=windows.sort_values('cobertura_2500',ascending=False).iloc[0]['versao']
        for v in list(adv.TITLES)+[best]:
            g=curve[(curve.recuperador==retriever)&(curve.versao==v)].groupby('orcamento').cobertura.mean()
            ax.plot(g.index,g.values,marker='o',label=v)
        ax.set(title=retriever+' — 17 perguntas de ajuste',xlabel='Orçamento real do contexto (tokens)',ylim=(0,1.02),xticks=list(adv.BUDGETS));ax.grid(alpha=.2)
        ax.legend(fontsize=7,loc='upper left')
    axes[0].set_ylabel('Cobertura média dos intervalos esperados')
    fig.tight_layout();fig.savefig(report/'curva_orcamento.png',dpi=150);plt.close(fig)
    windows=curve[curve.versao.str.startswith('paragrafo_janela_')].copy();windows['tamanho']=windows.versao.str.split('_').str[-1].astype(int)
    fig,axes=plt.subplots(1,2,figsize=(12,6),sharey=True)
    for ax,retriever in zip(axes,('BM25','BGE-M3')):
        table=windows[windows.recuperador==retriever].groupby(['tamanho','orcamento']).cobertura.mean().unstack().sort_index()
        im=ax.imshow(table.values,vmin=0,vmax=1,cmap='YlGnBu',aspect='auto')
        for i in range(table.shape[0]):
            for j in range(table.shape[1]):ax.text(j,i,f'{table.iloc[i,j]*100:.0f}%',ha='center',va='center',fontsize=9,color='white' if table.iloc[i,j]>.55 else 'black')
        ax.set(xticks=range(len(table.columns)),xticklabels=table.columns,yticks=range(len(table.index)),yticklabels=table.index,
            xlabel='Orçamento do contexto',title=retriever+' — varredura de janela ao redor')
    axes[0].set_ylabel('Teto por janela expandida (tokens)');fig.colorbar(im,ax=list(axes),label='Cobertura média',fraction=.025,pad=.03)
    fig.subplots_adjust(left=.09,right=.88,bottom=.12,top=.9,wspace=.15);fig.savefig(report/'varredura_janelas.png',dpi=150);plt.close(fig)
    old=curve[(curve.orcamento==2500)&curve.query_id.isin(exp.ORIGINAL_EIGHT)]
    fig,axes=plt.subplots(2,1,figsize=(16,9),sharex=True)
    for ax,retriever in zip(axes,('BM25','BGE-M3')):
        table=old[old.recuperador==retriever].pivot(index='query_id',columns='versao',values='cobertura')
        table=table.reindex(columns=list(adv.TITLES)+[f'paragrafo_janela_{n}' for n in exp.context.WINDOW_SIZES])
        ax.imshow(table.values,vmin=0,vmax=1,cmap='YlGnBu',aspect='auto')
        for i in range(len(table.index)):
            for j in range(len(table.columns)):ax.text(j,i,f'{100*table.iloc[i,j]:.0f}',ha='center',va='center',fontsize=7,color='white' if table.iloc[i,j]>.55 else 'black')
        ax.set(yticks=range(len(table.index)),yticklabels=[f'P{int(q.split("_")[1]):02d}' for q in table.index],title=retriever+' — cobertura por pergunta em 2.500 tokens (%)')
        ax.set_xticks(range(len(table.columns)),table.columns,rotation=40,ha='right')
    fig.tight_layout();fig.savefig(report/'oito_perguntas_por_variante.png',dpi=150);plt.close(fig)

def render(root):
    from IPython.display import display,Markdown,Image
    root=Path(root);report,_=locate(root)
    config=json.loads((report/'configuracao.json').read_text(encoding='utf-8'))
    assert audit.hash_file(report/'gabarito_snapshot.jsonl')==config['gabarito_sha256']
    for f in json.loads((report/'manifesto_resultados.json').read_text(encoding='utf-8'))['arquivos']:
        assert audit.hash_file(report/f['arquivo'])==f['sha256']
    verdict=json.loads((report/'veredicto.json').read_text(encoding='utf-8'))
    display(pd.read_csv(report/'status_perguntas_ajuste.csv'))
    display(pd.read_csv(report/'resumo_2500.csv').round(4));display(Image(filename=str(report/'curva_orcamento.png')))
    display(Image(filename=str(report/'varredura_janelas.png')))
    a=verdict['melhor_bge'];b=verdict['melhor_bm25'];p=verdict['comparacao']
    text=f"**Leitura do ajuste:** melhor BM25 observado: `{b['versao']}`, {100*b['cobertura_2500']:.1f}%; melhor BGE-M3: `{a['versao']}`, {100*a['cobertura_2500']:.1f}%. "
    text+=f"BGE contra BM25: {int(p['vitorias'])} vitórias, {int(p['empates'])} empates e {int(p['derrotas'])} derrotas; diferença média {100*p['delta_media']:.1f} p.p., IC bootstrap 95% [{100*p['ic95_inf']:.1f}; {100*p['ic95_sup']:.1f}]. "
    if p['ic95_inf']<=0<=p['ic95_sup']:text+='O intervalo inclui zero; a média não decide sozinha. '
    text+=verdict['ressalva']+' Cobertura mede evidência recuperada, não respostas geradas por LLM.'
    display(Markdown(text))
    display(Markdown('**Custo depois da expansão e do corte:** a tabela contabiliza o contexto entregue e o número de unidades distintas. Soma fixa de cinco resultados não é o critério principal.'))
    costs=pd.read_csv(report/'custo_orcamento_resumo.csv');display(costs[costs.orcamento==2500].round(1))
    display(Image(filename=str(report/'oito_perguntas_por_variante.png')))
    details=pd.read_csv(report/'diagnostico_por_pergunta.csv');queries,_=perguntas_csv.load(root);byid={q['query_id']:q for q in queries}
    for qid in exp.ORIGINAL_EIGHT:
        display(Markdown(f"**{qid} — {byid[qid]['pergunta']}**"))
        display(details[details.query_id==qid][['recuperador','versao','cobertura','documento_5','primeiro_rank_documento',
            'unidades_minimas','perda_evidencia_encoder','explicacao']].round(4))
    display(Markdown('Documento@5 é diagnóstico secundário; a cobertura usa todo o ranking até preencher o orçamento. Fragmentação é um fator estrutural, não uma explicação causal automática. Os CSVs conservam os intervalos efetivamente entregues e o diagnóstico das 17 perguntas.'))
    pairs=pd.read_csv(report/'bootstrap_pareado.csv')
    focused=pairs[((pairs.a.str.contains('paragrafo_janela_'))&(pairs.b.str.endswith(' / paragrafo')))|
        ((pairs.b.str.contains('paragrafo_janela_'))&(pairs.a.str.endswith(' / paragrafo')))]
    display(Markdown('**Bootstrap pareado — janelas ao redor versus parágrafo simples:** coortes de oito e 17 perguntas separadas.'))
    display(focused.round(4))
    display(Markdown('**Seção/tema: truncamento real e dependência dos acertos**'))
    trunc=pd.read_csv(report/'truncamento_secao_real.csv');display(trunc.groupby('escopo').agg(
        unidades=('chunk_id','size'),acima_8192_sem_especiais=('tokens_sem_especiais',lambda s:int((s>8192).sum())),
        truncadas_encoder=('truncado','sum'),maximo_tokens=('tokens_com_especiais','max')))
    ab=pd.read_csv(report/'ablacao_truncamento_secao.csv');display(ab[ab.orcamento==2500][['query_id','cobertura','cobertura_sem_unidades_truncadas',
        'delta_remocao','evidencia_em_unidades_truncadas','evidencia_entregue_fora_prefixo_encoder']].round(4))
    display(Markdown('A ablação refaz o preenchimento do orçamento após retirar unidades truncadas. Ela separa depender da unidade longa de depender do conteúdo que o encoder descartou. A auditoria ampla codifica as sete seções longas do corpus maior; os contrafactuais de recuperação se referem ao corpus idêntico do piloto. Não se atribui a essas seções uma vantagem em perguntas para as quais não participaram da busca.'))
    display(Markdown('**Reserva:** sete perguntas continuam congeladas. As 23 consultas executadas são somente de ajuste; três controles comportamentais e três perguntas ainda sem intervalo não recebem nota de suporte.'))
    return report
