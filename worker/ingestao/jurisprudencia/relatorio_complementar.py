"""Gráficos e diagnóstico do corpus enriquecido, separados do teste anterior."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from . import audit

LABELS={'fixa_500_o100':'Janela 500 + 20% de sobreposição',
        'paragrafo_janela_500':'Parágrafo + janela de 500'}


def locate(root):
    root=Path(root)
    pointer=json.loads((root/'dados/relatorios/jurisprudencia/complementar/ativa.json').read_text(encoding='utf-8'))
    return root/pointer['pasta_relatorios'],root/pointer['pasta_dados']


def finalize(root):
    report,data=locate(root)
    cfg=json.loads((report/'configuracao.json').read_text(encoding='utf-8'))
    completed=json.loads((report/'concluido.json').read_text(encoding='utf-8'))
    assert completed['protocolo_sha256']==audit.hash_file(report/'protocolo_complementar.json')
    frame=pd.read_csv(report/'cobertura.csv');pairs=pd.read_csv(report/'bootstrap.csv')
    primary=frame[(frame.coorte=='reserva_ja_exposta')&(frame.recuperador=='BGE-M3')&frame.cobertura.notna()]
    table=primary[primary.orcamento.eq(2500)].pivot(index='query_id',columns='versao',values='cobertura')
    table['delta_fixa_menos_paragrafo']=table.fixa_500_o100-table.paragrafo_janela_500
    table['resultado']=table.delta_fixa_menos_paragrafo.map(lambda d:'vitória da janela fixa' if d>1e-12 else ('vitória do parágrafo' if d< -1e-12 else 'empate'))
    table.to_csv(report/'comparacao_por_pergunta.csv')
    root=Path(root)
    old_pointer=json.loads((root/'dados/relatorios/jurisprudencia/teste_final/ativa.json').read_text(encoding='utf-8'))
    old=pd.read_csv(root/old_pointer['pasta_relatorios']/'cobertura.csv')
    old=old[old.orcamento.eq(2500)&old.cobertura.notna()][['query_id','versao','cobertura']].rename(columns={'cobertura':'cobertura_corpus_18'})
    new=primary[primary.orcamento.eq(2500)][['query_id','versao','cobertura']].rename(columns={'cobertura':'cobertura_corpus_ampliado'})
    before_after=old.merge(new,on=['query_id','versao'],validate='one_to_one')
    before_after.to_csv(report/'efeito_ampliacao_corpus.csv',index=False)
    pair=pairs[(pairs.coorte=='reserva_ja_exposta')&(pairs.recuperador=='BGE-M3')].iloc[0].to_dict()
    gold={q['query_id']:q for q in [json.loads(x) for x in (report/'gabarito_snapshot.jsonl').read_text(encoding='utf-8').splitlines()]}
    cluster_rows=[]
    for qid,row in table.iterrows():
        refs={r['registro_id'] for group in gold[qid]['alternativas_suporte'] for r in group}
        assert len(refs)==1, 'Esta sensibilidade requer uma fonte documental por pergunta principal.'
        cluster_rows.append(dict(documento=next(iter(refs)),delta=row['delta_fixa_menos_paragrafo']))
    grouped=pd.DataFrame(cluster_rows).groupby('documento').delta.agg(['sum','size'])
    rng=np.random.default_rng(cfg['seed'])
    draws=rng.integers(0,len(grouped),size=(2000,len(grouped)))
    sample=grouped['sum'].to_numpy()[draws].sum(axis=1)/grouped['size'].to_numpy()[draws].sum(axis=1)
    cluster=dict(documentos=len(grouped),perguntas=len(table),delta_media=float(table.delta_fixa_menos_paragrafo.mean()),
        ic95_inf=float(np.quantile(sample,.025)),ic95_sup=float(np.quantile(sample,.975)),replicas=2000,seed=cfg['seed'])
    audit.write_json(report/'bootstrap_sensibilidade_documento.json',cluster)
    means=primary[primary.orcamento.eq(2500)].groupby('versao').cobertura.mean()
    if pair['ic95_inf']>0:
        verdict='A janela fixa teve vantagem pareada com intervalo bootstrap acima de zero nesta avaliação complementar.'
        recommendation='fixa_500_o100'
    elif pair['ic95_sup']<0:
        verdict='O parágrafo com expansão teve vantagem pareada com intervalo bootstrap abaixo de zero nesta avaliação complementar.'
        recommendation='paragrafo_janela_500'
    else:
        verdict='O intervalo bootstrap inclui zero: não há superioridade estatística demonstrada entre as finalistas.'
        recommendation=means.idxmax()
    if (pair['ic95_inf']>0 or pair['ic95_sup']<0) and cluster['ic95_inf']<=0<=cluster['ic95_sup']:
        verdict+=' A sensibilidade por documento inclui zero; a conclusão não é robusta ao agrupamento das perguntas do mesmo acórdão.'
    record=dict(veredicto=verdict,comparacao=pair,sensibilidade_por_documento=cluster,maior_cobertura_observada=means.idxmax(),
        candidata_operacional=recommendation,criterio_candidata='Maior cobertura observada na comparação complementar; não houve novo ajuste de tamanho ou sobreposição.',
        corpus_documentos=completed['corpus_documentos'],consultas_executadas=30,perguntas_primarias_com_intervalos=6,
        fontes_suporte_no_corpus=6,
        limites=['Avaliação complementar de perguntas já expostas; não é teste cego independente.',
            'Corpus enriquecido dirigido pelas referências; não representa toda a base nem sua distribuição natural.',
            'Apenas seis perguntas pontuáveis na coorte principal; bootstrap pequeno não garante estabilidade.',
            'P15 e P16 compartilham acórdão e evidências. A sensibilidade por documento usa cinco grupos; o bootstrap por pergunta não torna essas observações independentes.',
            'P09 usa caso contrastivo com punições anteriores, não decisão direta de dispensa sem advertência.',
            'P15 usa humilhação reiterada e um valor de um julgamento; não estima valores usuais de indenização.',
            'As 17 perguntas de ajuste são exibidas separadamente; não viram novas perguntas de teste.',
            'Não houve geração de respostas por LLM nem avaliação comportamental de P30.'])
    sensitivity=json.loads((report/'sensibilidade_equivalentes.json').read_text(encoding='utf-8'))
    assert sensitivity['gabarito_original_sha256']==audit.hash_file(report/'gabarito_snapshot.jsonl')
    record['sensibilidade_referencias_equivalentes']=pd.read_csv(report/'sensibilidade_equivalentes_resumo.csv').to_dict('records')
    record['limites'].append('P16 e P21 recuperaram suporte em acórdãos não anotados no gabarito inicial. A análise posterior de alternativas é separada; zero na referência inicial não prova ausência de suporte jurídico.')
    audit.write_json(report/'veredicto.json',record)
    diagnostics=pd.read_csv(report/'diagnostico.csv')
    # Custos de contexto em 2.500 tokens e estrutura são separados de tamanho de unidade indexada.
    primary[primary.orcamento.eq(2500)].groupby('versao').agg(
        mediana=('tokens_utilizados','median'),p90=('tokens_utilizados',lambda s:s.quantile(.9)),maximo=('tokens_utilizados','max'),
        unidades_medias=('unidades_distintas','mean')).to_csv(report/'custo_contexto_2500.csv')
    structural=diagnostics[(diagnostics.coorte=='reserva_ja_exposta')&(diagnostics.recuperador=='BGE-M3')].groupby('versao').agg(
        taxa_fragmentacao_indice=('evidencia_fragmentada','mean'),unidades_minimas_media=('unidades_minimas','mean'),
        evidencia_perdida_encoder_media=('perda_evidencia_encoder','mean'),
        documento_no_contexto_taxa=('documento_no_contexto','mean'))
    structural.to_csv(report/'estrutura_evidencia_resumo.csv')
    trunc=pd.read_csv(report/'truncamento_encoder.csv')
    trunc.groupby('indice').agg(unidades=('chunk_id','size'),unidades_truncadas=('truncado','sum'),
        tokens_encoder_max=('tokens_encoder','max')).to_csv(report/'truncamento_resumo.csv')
    plot(report,primary,table,diagnostics)
    names=['configuracao.json','protocolo_complementar.json','concluido.json','cobertura.csv','contextos.csv','diagnostico.csv',
        'resumo_2500.csv','bootstrap.csv','auditoria_unidades.csv','truncamento_encoder.csv','comparacao_por_pergunta.csv',
        'veredicto.json','bootstrap_sensibilidade_documento.json','custo_contexto_2500.csv','estrutura_evidencia_resumo.csv','efeito_ampliacao_corpus.csv','truncamento_resumo.csv',
        'gabarito_sensibilidade_equivalentes.jsonl','sensibilidade_equivalentes.json','sensibilidade_equivalentes_cobertura.csv',
        'sensibilidade_equivalentes_resumo.csv','sensibilidade_equivalentes_bootstrap.csv',
        'complementar_curvas.png','complementar_por_pergunta.png','complementar_ajuste.png','complementar_sensibilidade.png']
    audit.write_json(report/'manifesto_resultados.json',dict(arquivos={n:audit.hash_file(report/n) for n in names}))
    return report,record


def plot(report,primary,table,diagnostics):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(13,4.8))
    for v,g in primary.groupby('versao'):
        avg=g.groupby('orcamento').cobertura.mean()
        axes[0].plot(avg.index,avg.values,marker='o',label=LABELS[v])
    axes[0].set(title='Seis perguntas — BGE-M3 — gabarito inicial',xlabel='Orçamento de contexto (tokens)',ylabel='Cobertura média',ylim=(-.02,1.02),xticks=[500,1000,2500,5000])
    axes[0].legend(fontsize=8);axes[0].grid(alpha=.2)
    means=primary[primary.orcamento.eq(2500)].groupby('versao').cobertura.mean()
    bars=axes[1].bar([LABELS[v] for v in means.index],means.values,color=['#326780','#d48b35'])
    axes[1].bar_label(bars,labels=[f'{100*x:.2f}%' for x in means],padding=4)
    axes[1].set(ylim=(0,1.08),ylabel='Cobertura@2500',title='Mesmo corpus e orçamento para as duas finalistas')
    axes[1].tick_params(axis='x',labelsize=9)
    fig.suptitle('Avaliação complementar: documentos de suporte + distratores; sem novo ajuste',fontsize=12)
    fig.tight_layout();fig.savefig(report/'complementar_curvas.png',dpi=150);plt.close(fig)
    values=table[list(LABELS)]
    fig,ax=plt.subplots(figsize=(10,5))
    im=ax.imshow(values.values,aspect='auto',vmin=0,vmax=1,cmap='YlGnBu')
    for i in range(len(values)):
        for j in range(2):
            val=values.iloc[i,j];ax.text(j,i,f'{val*100:.1f}%',ha='center',va='center',color='white' if val>.55 else 'black')
    ax.set(yticks=range(len(values)),yticklabels=[q.replace('juris_','P') for q in values.index],
        xticks=[0,1],xticklabels=list(LABELS.values()),title='Cobertura das referências iniciais — 2.500 tokens — BGE-M3')
    fig.colorbar(im,ax=ax,label='Fração da evidência anotada coberta')
    fig.text(.02,.045,'P16/P21: há suporte em outros acórdãos; veja a análise posterior de referências equivalentes.',fontsize=8)
    fig.text(.02,.015,'P30: busca executada, cobertura não aplicável (controle comportamental, sem LLM).',fontsize=8)
    fig.tight_layout(rect=(0,.09,1,1));fig.savefig(report/'complementar_por_pergunta.png',dpi=150);plt.close(fig)
    frame=pd.read_csv(report/'cobertura.csv');dev=frame[(frame.coorte=='ajuste_anterior')&(frame.recuperador=='BGE-M3')&frame.orcamento.eq(2500)&frame.cobertura.notna()]
    t=dev.pivot(index='query_id',columns='versao',values='cobertura')
    fig,ax=plt.subplots(figsize=(13,4.5));x=np.arange(len(t));width=.38
    for j,v in enumerate(LABELS):ax.bar(x+(j-.5)*width,t[v],width,label=LABELS[v])
    ax.set(xticks=x,xticklabels=[q.replace('juris_','P') for q in t.index],ylim=(0,1.08),ylabel='Cobertura@2500',title='17 perguntas de ajuste no corpus ampliado — diagnóstico separado')
    ax.legend(fontsize=8);fig.tight_layout();fig.savefig(report/'complementar_ajuste.png',dpi=150);plt.close(fig)
    sensitivity=pd.read_csv(report/'sensibilidade_equivalentes_cobertura.csv')
    s=sensitivity[(sensitivity.coorte=='reserva_ja_exposta')&(sensitivity.recuperador=='BGE-M3')&sensitivity.orcamento.eq(2500)]
    fig,ax=plt.subplots(figsize=(11,4.5));x=np.arange(2);width=.35
    for i,(column,label) in enumerate([('cobertura_gabarito_original','Gabarito inicial'),('cobertura','Referências ampliadas após inspeção')]):
        means=s.groupby('versao')[column].mean().reindex(list(LABELS))
        bars=ax.bar(x+(i-.5)*width,means,width,label=label)
        ax.bar_label(bars,labels=[f'{100*v:.2f}%' for v in means],padding=4)
    ax.set(xticks=x,xticklabels=list(LABELS.values()),ylim=(0,1.08),ylabel='Cobertura@2500',title='Sensibilidade às referências anotadas — mesmas buscas e contextos')
    ax.legend(fontsize=9);fig.text(.02,.015,'Ampliação posterior de P16/P21: análise exploratória; não substitui a comparação principal nem constitui novo teste cego.',fontsize=8)
    fig.tight_layout(rect=(0,.05,1,1));fig.savefig(report/'complementar_sensibilidade.png',dpi=150);plt.close(fig)


def render(root):
    from IPython.display import display, Markdown, Image
    report,_=locate(root)
    manifest=json.loads((report/'manifesto_resultados.json').read_text(encoding='utf-8'))
    for name,digest in manifest['arquivos'].items():assert audit.hash_file(report/name)==digest
    cfg=json.loads((report/'configuracao.json').read_text(encoding='utf-8'));verdict=json.loads((report/'veredicto.json').read_text(encoding='utf-8'))
    display(Markdown(f"**Corpus complementar:** {cfg['documentos_total']} acórdãos. Foram mantidos os 18 anteriores e incluído todo o lote de candidatos já levantado, sem filtrar pelo desempenho. Os trechos de referência das seis perguntas estão agora no índice de ambas as estratégias. O teste anterior de cobertura zero permanece preservado. **Esta rodada é complementar, com perguntas já expostas.**"))
    display(pd.read_csv(report/'resumo_2500.csv'))
    display(Image(filename=str(report/'complementar_curvas.png')))
    display(Image(filename=str(report/'complementar_por_pergunta.png')))
    display(pd.read_csv(report/'comparacao_por_pergunta.csv'))
    display(Markdown('**Leitura dos zeros e sensibilidade do gabarito:** P16 e P21 tiveram trechos relevantes de outros acórdãos no contexto. Foram verificadas três alternativas adicionais nesses dois casos, mantendo corpus, rankings, contextos e o gabarito inicial. A tabela abaixo é **posterior à inspeção**, não substitui a comparação principal e não é um novo teste cego. A cobertura mede referências anotadas; não equivale à correção de uma resposta gerada.'))
    display(pd.read_csv(report/'sensibilidade_equivalentes_resumo.csv'))
    display(Image(filename=str(report/'complementar_sensibilidade.png')))
    sensitivity=pd.read_csv(report/'sensibilidade_equivalentes_cobertura.csv')
    display(sensitivity[(sensitivity.coorte=='reserva_ja_exposta')&(sensitivity.recuperador=='BGE-M3')&sensitivity.orcamento.eq(2500)][['query_id','versao','cobertura_gabarito_original','cobertura']])
    display(Markdown('**Efeito da ampliação do corpus:** a tabela compara as mesmas perguntas e parâmetros em bases diferentes. A diferença não é ganho causado pelo chunking nem um novo resultado cego.'))
    display(pd.read_csv(report/'efeito_ampliacao_corpus.csv'))
    display(Markdown('**Bootstrap pareado:** diferença = janela fixa − parágrafo. As coortes não são misturadas.'))
    display(pd.read_csv(report/'bootstrap.csv'))
    display(Markdown('**Sensibilidade por documento:** P15 e P16 compartilham acórdão. Reamostragem dos cinco grupos documentais, mantendo juntas suas perguntas; leitura complementar ao bootstrap principal por pergunta.'))
    display(pd.DataFrame([verdict['sensibilidade_por_documento']]))
    display(Markdown('**Diagnóstico de cada pergunta principal e dos casos P01/P02/P23:**'))
    diag=pd.read_csv(report/'diagnostico.csv')
    keep=(diag.coorte=='reserva_ja_exposta')|diag.query_id.isin(['juris_001','juris_002','juris_023'])
    cols=['query_id','versao','cobertura','primeiro_rank_documento','primeiro_rank_evidencia','evidencia_fragmentada','unidades_minimas','perda_evidencia_encoder','explicacao']
    display(diag[(diag.recuperador=='BGE-M3')&keep][cols])
    display(Markdown('**Custos e integridade:** tamanho das unidades indexadas e custo do contexto entregue são medidas diferentes. Fragmentação refere-se ao índice; a expansão pode recuperar evidência fora do parágrafo indexado.'))
    display(pd.read_csv(report/'auditoria_unidades.csv'));display(pd.read_csv(report/'custo_contexto_2500.csv'))
    display(pd.read_csv(report/'estrutura_evidencia_resumo.csv'))
    display(Markdown('**Truncamento real do encoder:** BGE-M3 usa limite de 8.192 tokens incluindo os especiais. Unidades acima de 512 tokens não são automaticamente truncadas neste encoder.'))
    display(pd.read_csv(report/'truncamento_resumo.csv'))
    display(Image(filename=str(report/'complementar_ajuste.png')))
    display(Markdown('**Veredicto:** '+verdict['veredicto']))
    display(Markdown('**Candidata operacional nesta comparação:** '+LABELS[verdict['candidata_operacional']]+'. '+verdict['criterio_candidata']))
    display(Markdown('**Limites de interpretação:**\n\n'+'\n'.join('- '+x for x in verdict['limites'])))
    return report
