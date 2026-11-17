"""Apresentação do ajuste equilibrado e do teste reservado, sem repetir consultas."""
from pathlib import Path
import json
import numpy as np,pandas as pd
from . import audit,finalistas_chunking as adjustment,teste_final_chunking as final,chunking_avancado as adv

def locate(root,phase):
    root=Path(root);pointer=json.loads((root/f'dados/relatorios/jurisprudencia/{phase}/ativa.json').read_text(encoding='utf-8'))
    return root/pointer['pasta_relatorios'],pointer

def paired_oriented(frame,a,b):
    row=frame[(frame.a==a)&(frame.b==b)]
    if len(row):return row.iloc[0].to_dict()
    r=frame[(frame.a==b)&(frame.b==a)].iloc[0]
    return dict(a=a,b=b,n=int(r.n),vitorias=int(r.derrotas),empates=int(r.empates),derrotas=int(r.vitorias),
        delta_media=-float(r.delta_media),ic95_inf=-float(r.ic95_sup),ic95_sup=-float(r.ic95_inf))

def finalize_adjustment(root):
    root=Path(root);report,pointer=locate(root,'finalistas');data=root/pointer['pasta_dados']
    cfg=json.loads((report/'configuracao.json').read_text(encoding='utf-8'))
    assert cfg['codigo_sha256']==audit.hash_file(adjustment.__file__)
    assert cfg['gabarito_sha256']==audit.hash_file(report/'gabarito_ajuste_snapshot.jsonl')
    assert cfg['gabarito_sha256']==audit.hash_file(root/'avaliacao/dados/jurisprudencia/perguntas_suporte.jsonl')
    curve=pd.read_csv(report/'cobertura_ajuste.csv');summary=pd.read_csv(report/'resumo_2500.csv')
    assert curve.query_id.nunique()==23 and curve.groupby(['versao','recuperador','orcamento']).cobertura.count().eq(17).all()
    assert (curve.tokens_utilizados<=curve.orcamento).all()
    selected=json.loads((report/'finalistas_selecionadas.json').read_text(encoding='utf-8'));assert len(selected)==2
    a='BGE-M3 / '+selected[0]['versao'];b='BGE-M3 / '+selected[1]['versao']
    pair=paired_oriented(pd.read_csv(report/'bootstrap_ajuste.csv'),a,b)
    audit.write_json(report/'comparacao_finalistas_ajuste.json',pair)
    plot_adjustment(report)
    _manifest(report)
    return report,pair

def _manifest(report):
    (report/'executado_relatorio_finalistas.py').write_bytes(Path(__file__).read_bytes())
    files=[p for p in report.iterdir() if p.is_file() and p.name!='manifesto_resultados.json']
    audit.write_json(report/'manifesto_resultados.json',dict(arquivos=[dict(arquivo=p.name,sha256=audit.hash_file(p)) for p in sorted(files)]))

def verify_manifest(report):
    for f in json.loads((report/'manifesto_resultados.json').read_text(encoding='utf-8'))['arquivos']:
        assert audit.hash_file(report/f['arquivo'])==f['sha256']

def plot_adjustment(report):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    curve=pd.read_csv(report/'cobertura_ajuste.csv');curve=curve[(curve.recuperador=='BGE-M3')&curve.cobertura.notna()]
    fig,axes=plt.subplots(1,2,figsize=(14,5),sharey=True)
    for ax,prefix,title in zip(axes,('fixa_','paragrafo_janela_'),('Janela fixa — tamanhos e sobreposição','Parágrafo + janela ao redor')):
        for version,g in curve[curve.versao.str.startswith(prefix)].groupby('versao'):
            avg=g.groupby('orcamento').cobertura.mean();ax.plot(avg.index,avg.values,marker='o',label=version)
        ax.set(title=title,xlabel='Orçamento real (tokens)',xticks=list(adv.BUDGETS),ylim=(0,1.02));ax.grid(alpha=.2);ax.legend(fontsize=7,loc='upper left')
    axes[0].set_ylabel('Cobertura média — 17 perguntas de ajuste');fig.tight_layout();fig.savefig(report/'grade_justa_curvas.png',dpi=150);plt.close(fig)
    summary=pd.read_csv(report/'resumo_2500.csv');summary=summary[summary.recuperador=='BGE-M3']
    fig,axes=plt.subplots(1,2,figsize=(14,6))
    for ax,prefix,title in zip(axes,('fixa_','paragrafo_janela_'),('Janela fixa','Parágrafo + janela')):
        g=summary[summary.versao.str.startswith(prefix)].sort_values('cobertura_2500')
        ax.barh(g.versao,g.cobertura_2500,color='#336c8b');ax.set(xlim=(0,1),xlabel='Cobertura@2500',title=title)
        for i,r in enumerate(g.itertuples()):ax.text(r.cobertura_2500+.01,i,f'{100*r.cobertura_2500:.1f}%',va='center',fontsize=8)
    fig.tight_layout();fig.savefig(report/'grade_justa_2500.png',dpi=150);plt.close(fig)

def finalize_final(root):
    root=Path(root);report,_=locate(root,'teste_final');completed=json.loads((report/'concluido.json').read_text(encoding='utf-8'))
    config=json.loads((report/'configuracao.json').read_text(encoding='utf-8'));protocol=final.load_protocol(root)
    assert completed['protocolo_sha256']==protocol['sha256']==config['protocolo_sha256']
    assert audit.hash_file(report/'gabarito_snapshot.jsonl')==config['gabarito_sha256']
    curve=pd.read_csv(report/'cobertura.csv');summary=pd.read_csv(report/'resumo_2500.csv')
    assert curve.query_id.nunique()==7 and len(curve.versao.unique())==2
    assert (curve.tokens_utilizados<=curve.orcamento).all()
    pairs=pd.read_csv(report/'bootstrap_final.csv');pair=pairs.iloc[0].to_dict() if len(pairs) else None
    valid=curve[curve.cobertura.notna()&(curve.orcamento==2500)]
    conditional=valid[valid.documento_suporte_no_corpus.eq(True)].groupby('versao').agg(
        cobertura_condicional_2500=('cobertura','mean'),perguntas=('query_id','size')).reset_index()
    conditional.to_csv(report/'resumo_condicional_corpus.csv',index=False)
    present=int(valid.drop_duplicates('query_id').documento_suporte_no_corpus.sum())
    if not len(valid):verdict='As consultas foram executadas, mas nenhuma é elegível para cobertura por intervalo; não há vencedor nesta métrica.'
    elif present==0:verdict='As fontes de referência não estavam no corpus congelado. O resultado mede ausência de cobertura da base; empate não demonstra equivalência entre os chunkings.'
    elif pair and pair['ic95_inf']<=0<=pair['ic95_sup']:verdict='A diferença pareada no teste reservado inclui zero no intervalo bootstrap. O maior valor observado não estabelece vencedor definitivo.'
    else:verdict='Há diferença observada entre as finalistas neste conjunto reservado; a conclusão permanece circunscrita ao corpus e às perguntas avaliadas.'
    record=dict(veredicto=verdict,comparacao=pair,fontes_disponiveis_no_corpus=present,
        perguntas_com_intervalo=valid.query_id.nunique(),consultas_executadas=7,
        limitacao='Reserva prospectiva, conforme registro histórico. Não é teste externo independente; corpus de 18 documentos e amostra pequena.',
        controle_comportamental='Busca executada; respostas de LLM e sua abstenção não são avaliadas neste experimento de chunking.')
    audit.write_json(report/'veredicto.json',record)
    plot_final(report);_manifest(report)
    return report,record

def plot_final(report):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    curve=pd.read_csv(report/'cobertura.csv');valid=curve.dropna(subset=['cobertura'])
    fig,axes=plt.subplots(1,2,figsize=(13,5))
    for v,g in valid.groupby('versao'):
        avg=g.groupby('orcamento').cobertura.mean();axes[0].plot(avg.index,avg.values,marker='o',label=v)
    axes[0].set(xlabel='Orçamento (tokens)',ylabel='Cobertura média',ylim=(-.03,1.03),xticks=list(adv.BUDGETS),title='Teste reservado — parâmetros congelados');axes[0].legend(fontsize=8);axes[0].grid(alpha=.2)
    table=valid[valid.orcamento==2500].pivot(index='query_id',columns='versao',values='cobertura')
    if len(table):
        axes[1].imshow(table.values,aspect='auto',vmin=0,vmax=1,cmap='YlGnBu')
        for i in range(len(table.index)):
            for j in range(len(table.columns)):axes[1].text(j,i,f'{100*table.iloc[i,j]:.0f}%',ha='center',va='center',color='white' if table.iloc[i,j]>.55 else 'black')
        axes[1].set(yticks=range(len(table.index)),yticklabels=table.index,xticks=range(len(table.columns)),xticklabels=table.columns,title='Cobertura por pergunta em 2.500 tokens')
    else:axes[1].text(.5,.5,'Sem consultas elegíveis para cobertura',ha='center',va='center');axes[1].set_axis_off()
    fig.tight_layout();fig.savefig(report/'teste_final_curvas_e_perguntas.png',dpi=150);plt.close(fig)

def render_adjustment(root):
    from IPython.display import display,Markdown,Image
    report,_=locate(root,'finalistas');verify_manifest(report)
    cfg=json.loads((report/'configuracao.json').read_text(encoding='utf-8'))
    selected=json.loads((report/'finalistas_selecionadas.json').read_text(encoding='utf-8'));pair=json.loads((report/'comparacao_finalistas_ajuste.json').read_text(encoding='utf-8'))
    display(Markdown('**Diagnóstico de P01, P02 e P23 — janela fixa de 500 sem sobreposição:**'))
    d=json.loads((report/'diagnostico_p01_p02_p23.json').read_text(encoding='utf-8'))
    display(pd.DataFrame([{k:r[k] for k in ('query_id','documento_rank','primeiro_trecho_evidencia_rank','cobertura_real_2500','cobertura_oraculo_2500')} for r in d]))
    display(Markdown('P01 recuperou argumentos da empresa e decisão anterior reformada. P02 priorizou documentos sobre outras relações de emprego. P23 recuperou, entre outros trechos, um precedente de outro processo citado no acórdão. O gabarito considera fundamento/resultado próprios e ementas próprias equivalentes; o oráculo diagnóstico usa o gabarito apenas para estimar a cobertura alcançável, sem entrar na busca real.'))
    display(Markdown('**Cautela específica em P23:** o primeiro trecho já expressa a regra de dois anos em um precedente citado e pode ser útil para uma pergunta geral sobre prazo. Zero nos intervalos escolhidos não demonstra resposta jurídica errada. Esta métrica mede recuperação das referências anotadas; não é um gabarito exaustivo de toda passagem juridicamente válida nem uma avaliação de respostas geradas.'))
    display(pd.read_csv(report/'diagnostico_tres_perguntas_por_grade.csv').round(4))
    display(Markdown('**Comparação equilibrada: sete configurações por família, mesmo corpus de 18 documentos e mesmo orçamento.**'))
    display(pd.read_csv(report/'auditoria_grade.csv').round(3))
    display(Markdown('A reconstrução considera a união dos intervalos, sem contar a sobreposição duas vezes. A sobreposição-alvo pode variar um token ao retokenizar a fatia; a tabela mostra o valor efetivamente medido e o custo do índice.'))
    display(pd.read_csv(report/'resumo_2500.csv').round(4));display(Image(filename=str(report/'grade_justa_curvas.png')));display(Image(filename=str(report/'grade_justa_2500.png')))
    display(pd.DataFrame(selected).round(4))
    display(Markdown(f"**Bootstrap pareado entre as finalistas no ajuste:** {int(pair['vitorias'])} vitórias, {int(pair['empates'])} empates e {int(pair['derrotas'])} derrotas para `{pair['a']}` contra `{pair['b']}`; diferença {100*pair['delta_media']:.1f} p.p., IC95% [{100*pair['ic95_inf']:.1f}; {100*pair['ic95_sup']:.1f}]. Seleção e comparação são exploratórias nesta fase; o teste reservado vem depois do congelamento."))
    display(Markdown('As alternativas de ementa de P01/P02/P23 foram acrescentadas durante o ajuste. As métricas das duas famílias foram recalculadas com o mesmo gabarito atualizado; não se misturam os valores históricos da versão anterior.'))
    return report

def render_final(root):
    from IPython.display import display,Markdown,Image
    root=Path(root);report,_=locate(root,'teste_final');verify_manifest(report)
    config=json.loads((report/'configuracao.json').read_text(encoding='utf-8'));verdict=json.loads((report/'veredicto.json').read_text(encoding='utf-8'))
    gold=[json.loads(line) for line in (report/'gabarito_snapshot.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    display(Markdown('**Teste reservado concluído uma vez.** As saídas abaixo são lidas do relatório; esta célula não faz novas buscas.'))
    display(pd.DataFrame([dict(query_id=q['query_id'],pergunta=q['pergunta'],avaliacao=q.get('avaliacao','suporte_intervalos'),
        resposta_de_referencia=q.get('resposta_esperada','')) for q in gold]))
    display(pd.read_csv(report/'resumo_2500.csv').round(4));display(Image(filename=str(report/'teste_final_curvas_e_perguntas.png')))
    display(Markdown('**Diagnóstico secundário: cobertura somente nas perguntas com alguma alternativa integralmente disponível no corpus congelado.**'))
    display(pd.read_csv(report/'resumo_condicional_corpus.csv').round(4))
    display(pd.read_csv(report/'cobertura.csv').query('orcamento == 2500')[['query_id','versao','cobertura','documento_suporte_no_corpus','avaliacao','tokens_utilizados']].round(4))
    display(pd.read_csv(report/'bootstrap_final.csv').round(4))
    display(Markdown('**Veredicto:** '+verdict['veredicto']+' '+verdict['limitacao']))
    display(Markdown('As fontes usadas para anotar as sete perguntas foram registradas antes da busca das finalistas. Uma referência externa ao índice não foi acrescentada ao corpus após o congelamento. Perguntas comportamentais, quando presentes, têm busca registrada e cobertura indefinida; não há geração ou julgamento de resposta por LLM nesta etapa.'))
    print('Protocolo congelado SHA-256:',config['protocolo_sha256'])
    return report
