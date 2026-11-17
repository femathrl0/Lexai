"""Leitura leve do andamento e dos artefatos do notebook 05."""
from pathlib import Path
from collections import Counter
import json
import pandas as pd
import pyarrow.parquet as pq
from . import audit,chunking_definitivo as pipeline


def load(root):
    root=Path(root).resolve()
    pointer=json.loads((root/'dados/relatorios/jurisprudencia/chunking_definitivo/ativa.json').read_text(encoding='utf-8'))
    report=pipeline.within(root,pointer['pasta_relatorios'],'dados/relatorios/jurisprudencia/chunking_definitivo')
    data=pipeline.within(root,pointer['pasta_dados'],'dados/chunks/jurisprudencia/definitivo')
    config=json.loads((report/'configuracao.json').read_text(encoding='utf-8'))
    assert pipeline.canonical(config)==pointer['identidade']
    progressfile=report/'concluido.json' if (report/'concluido.json').exists() else report/'progresso.json'
    progress=json.loads(progressfile.read_text(encoding='utf-8')) if progressfile.exists() else dict(
        status='preparando',documentos_esperados=config['documentos_esperados'],documentos_processados=0,
        documentos_restantes=config['documentos_esperados'],chunks=0,lotes_concluidos=0)
    return dict(root=root,report=report,data=data,config=config,progress=progress,identity=pointer['identidade'])


def show_scope(root):
    from IPython.display import display,Markdown
    state=load(root);c=state['config']
    display(pd.DataFrame([dict(registros_entrada=c['corpus_entrada'],documentos_elegiveis=c['documentos_esperados'],
        fora_do_recorte=c['corpus_entrada']-c['documentos_esperados'],caracteres_elegiveis=c['caracteres_esperados'],
        tokens_por_janela=c['tamanho_tokens'],sobreposicao_alvo=c['sobreposicao_tokens'])]))
    display(pd.read_csv(state['report']/'escopo_por_arquivo.csv').drop(columns=['entrada_sha256']))
    display(Markdown('**Texto usado:** campo principal protegido indicado no notebook 03, sem concatenar ementa e inteiro teor. As exclusões do recorte são lógicas: os registros de origem continuam preservados.'))
    print('Versão do tokenizador:',c['revisao'])
    print('Hash da configuração:',state['identity'])
    return state


def verify_samples(root,limit=3):
    """Releitura de lotes já fechados. A validação global só existe após o corpus completo."""
    state=load(root);paths=sorted(state['report'].glob('lote_*.json'))
    if not paths:return pd.DataFrame(columns=['lote','documentos','chunks','reconstrucao','sha256'])
    selected=paths[:max(1,limit-1)]+([paths[-1]] if limit>1 and len(paths)>1 else [])
    selected=list(dict.fromkeys(selected));results=[]
    for path in selected:
        cp=json.loads(path.read_text(encoding='utf-8'))
        assert cp['configuracao_sha256']==state['identity']
        chunks=state['root']/cp['chunks_arquivo'];docs=state['root']/cp['documentos_arquivo']
        assert audit.hash_file(chunks)==cp['chunks_sha256'] and audit.hash_file(docs)==cp['documentos_sha256']
        table=pq.read_table(chunks)
        assert table.schema==pipeline.CHUNK_SCHEMA
        rows=table.to_pylist();summaries=pq.read_table(docs).to_pylist()
        pipeline.validate_partition(rows,summaries)
        results.append(dict(lote=path.stem,documentos=len(summaries),chunks=len(rows),reconstrucao='aprovada',sha256='conferido'))
    return pd.DataFrame(results)


def show_schema(root):
    from IPython.display import display
    state=load(root)
    display(pd.DataFrame([dict(campo=f.name,tipo=str(f.type)) for f in pipeline.CHUNK_SCHEMA]))
    files=sorted(state['data'].glob('chunks_*.parquet'))
    if files:
        sample=pq.read_table(files[0],columns=['chunk_id','registro_id','campo_texto','ordem','inicio','fim','tokens','sobreposicao_anterior_tokens','split_proposto']).to_pandas().head(5)
        for k in ('chunk_id','registro_id'):sample[k+'_prefixo']=sample.pop(k).str[:12]
        display(sample)
    print('Texto, relator e número de processo não são exibidos no painel de amostra.')


def show_progress(root):
    from IPython.display import display,Markdown
    state=load(root);p=state['progress']
    display(pd.DataFrame([{k:p.get(k) for k in ('status','documentos_esperados','documentos_processados',
        'documentos_restantes','chunks','lotes_concluidos','atualizado_em_utc')}]))
    display(Markdown('**Estado:** '+('corpus completo e validado; consulte o manifesto final.' if p['status']=='chunking_validado' else
        'processamento integral em andamento ou retomável. Os lotes fechados são válidos; a saída global ainda não deve ser tratada como corpus completo.')))
    print('Relatórios:',state['report'].relative_to(state['root']))
    print('Parquets:',state['data'].relative_to(state['root']))
    return state


def show_plots(root):
    import matplotlib.pyplot as plt
    state=load(root);scope=pd.read_csv(state['report']/'escopo_por_arquivo.csv')
    docs=Counter();chunks=Counter()
    for path in state['report'].glob('lote_*.json'):
        cp=json.loads(path.read_text(encoding='utf-8'));docs[cp['arquivo_id']]+=cp['documentos'];chunks[cp['arquivo_id']]+=cp['chunks']
    scope['processados']=scope.arquivo_id.map(docs).fillna(0).astype(int)
    scope['restantes']=scope.documentos_elegiveis-scope.processados
    if (scope.restantes<0).any():raise ValueError('Lotes excedem o recorte esperado.')
    fig,axes=plt.subplots(1,2,figsize=(13,5))
    scope.plot.barh(x='arquivo_id',y=['processados','restantes'],stacked=True,ax=axes[0],color=['#276b82','#dbe2e8'])
    axes[0].set(title='Cobertura do processamento por arquivo',xlabel='Documentos elegíveis',ylabel='Arquivo de origem')
    scope['chunks_gerados']=scope.arquivo_id.map(chunks).fillna(0).astype(int)
    axes[1].barh(scope.arquivo_id,scope.chunks_gerados,color='#276b82')
    axes[1].set(title='Chunks já gravados — não é previsão do total',xlabel='Chunks em lotes fechados',ylabel='Arquivo de origem')
    fig.suptitle('Janela 500 + sobreposição 100 — fotografia do andamento')
    fig.tight_layout();fig.savefig(state['report']/'andamento_chunking.png',dpi=140);plt.show()
    return scope


def show_outputs(root):
    from IPython.display import display,Markdown
    state=load(root)
    files=[('chunks_*.parquet','Texto do chunk, tokens, offsets, metadados e vínculos','por lote concluído'),
        ('documentos_*.parquet','Hash do texto-base e reconciliação por documento','por lote concluído'),
        ('configuracao.json','Regra, recorte, fontes e versões fixadas','criado'),
        ('lote_*.json','Hashes e contagens que permitem retomada','por lote concluído'),
        ('progresso.json','Fotografia de contagens e estado','atualizado durante execução'),
        ('manifesto_lotes.json','Lista integral dos lotes e respectivos hashes','gerado ao concluir e validar'),
        ('concluido.json','Resultado da auditoria global','gerado ao concluir e validar')]
    display(pd.DataFrame(files,columns=['artefato','conteudo','disponibilidade']))
    if (state['report']/'concluido.json').exists():
        for name in ('documentos_por_tribunal.csv','particoes_preservadas.csv','distribuicao_tokens.csv'):
            display(pd.read_csv(state['report']/name).head(25))
    display(Markdown('**Formato:** chunks e documentos são gravados em Parquet por lote, para leitura incremental. Os CSVs são tabelas agregadas de auditoria. O CSV limpo do notebook 03 permanece preservado; não se duplica todo o texto em um segundo CSV gigante.'))


def show_diagnosis(root):
    from IPython.display import display,Markdown
    state=load(root);p=state['progress']
    if p['status']=='chunking_validado':
        display(Markdown(f"**Chunking concluído e validado:** {p['documentos_processados']:,} documentos e {p['chunks']:,} chunks. IDs, hashes, reconstrução, limites e preservação dos grupos/partições passaram na auditoria global."))
    else:
        display(Markdown(f"**Configuração aplicada; execução integral ainda parcial:** {p['documentos_processados']:,} de {p['documentos_esperados']:,} documentos constam no último progresso salvo. O total de chunks é o efetivamente gerado até esse ponto. A validação global será executada automaticamente após o último lote."))
    display(Markdown('**Proteção de dados pessoais:** a entrada deriva do mascaramento de CPFs e do PLN conservador. O texto principal é conferido antes de ser dividido, e o marcador `[CPF_REMOVIDO]` não é cortado. Isso não equivale a anonimização integral: nomes e outros dados pessoais podem permanecer nos documentos e metadados.'))
    display(Markdown('**Repetições e partições:** não se elimina um chunk apenas porque seu texto coincide com outro; preservam-se documento e proveniência. A auditoria final conta IDs repetidos e cópias textuais separadamente, verifica os grupos de avaliação e mantém os splits propostos pelo notebook 03. Esses splits não são treinamento de modelo.'))
    display(Markdown('**Integração seguinte:** somente após `concluido.json` indicar `chunking_validado`, preparar embeddings BGE-M3 com configuração compatível com legislação e importar a coleção própria de jurisprudência no pgvector. Não houve geração de embeddings, criação de banco vetorial ou nova avaliação de respostas nesta etapa.'))
