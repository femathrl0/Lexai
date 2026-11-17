from pathlib import Path
import json
import pandas as pd
from . import chunking_definitivo_relatorio as previous


def state(root):
    root=Path(root);folder=root/'dados/relatorios/jurisprudencia/embeddings'
    out=dict(root=root,folder=folder,chunking=previous.load(root))
    for name in ('preflight','encadeamento','politica_execucao'):
        path=folder/(name+'.json');out[name]=json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
    pointer=folder/'ativa.json'
    if pointer.exists():
        p=json.loads(pointer.read_text(encoding='utf-8'));report=root/p['pasta_relatorios'];out['report']=report
        for name in ('configuracao','progresso','concluido','pgvector_concluido','progresso_pgvector'):
            path=report/(name+'.json');out[name]=json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
    return out


def show_preflight(root):
    from IPython.display import display,Markdown
    s=state(root);p=s['preflight']
    if p:
        fp=p['backbone'];display(pd.DataFrame([{k:fp[k] for k in ('modelo','revisao','dimensao','dtype','max_seq_length','normalizacao_l2','device')}]))
        display(pd.DataFrame([p['compatibilidade_legislacao']]).drop(columns=['observacao']))
        display(pd.DataFrame([p['benchmark']]))
        display(Markdown('**Compatibilidade:** os três vetores transitórios de prova foram confrontados com o cache original de legislação, cujo hash e mapeamento foram verificados. A legislação não foi regravada. A medição artificial serve apenas para custo de execução; não mede qualidade jurídica.'))
        display(pd.DataFrame([p['banco']]))
    else:display(Markdown('Pré-flight técnico ainda sem resultado salvo; não há afirmação de compatibilidade.'))
    display(pd.DataFrame([s['politica_execucao']]) if s['politica_execucao'] else pd.DataFrame([{'estado':'recurso ainda não definido'}]))
    return s


def show_progress(root):
    from IPython.display import display,Markdown
    s=state(root)
    if s.get('pgvector_concluido'):display(pd.DataFrame([s['pgvector_concluido']]))
    elif s.get('concluido'):display(pd.DataFrame([s['concluido']]))
    elif s.get('progresso'):display(pd.DataFrame([s['progresso']]))
    else:
        display(pd.DataFrame([dict(estado='aguardando_conclusao_validada_do_notebook_05',
            documentos_chunking_processados=s['chunking']['progress']['documentos_processados'],
            documentos_chunking_esperados=s['chunking']['config']['documentos_esperados'],
            embeddings_corpus_iniciados=False)]))
    if s['encadeamento']:display(pd.DataFrame([s['encadeamento']]))
    display(Markdown('**Separação de etapas:** o pré-flight não é vetorização integral. Cache parcial, lote concluído e coleção integral validada têm estados diferentes. Nenhuma taxa de acerto de respostas é inferida da existência de vetores.'))
    return s


def plots(root):
    import matplotlib.pyplot as plt
    s=state(root);fig,ax=plt.subplots(figsize=(9,3.5))
    p=s.get('progresso') or s.get('concluido')
    if p:
        ax.barh(['Vetores'],[p['chunks_vetorizados']],color='#276b82',label='Concluídos')
        ax.barh(['Vetores'],[p['chunks_restantes']],left=[p['chunks_vetorizados']],color='#dbe2e8',label='Restantes')
        ax.set(xlabel='Chunks do corpus validado',title='Andamento da vetorização');ax.legend()
    else:
        ax.text(.5,.5,'A geração integral aguarda o notebook 05 e a definição do recurso.',ha='center',va='center',wrap=True)
        ax.set_axis_off();ax.set_title('Embeddings de jurisprudência — preparação')
    fig.tight_layout();s['folder'].mkdir(parents=True,exist_ok=True);fig.savefig(s['folder']/'andamento_embeddings.png',dpi=140);plt.show()


def diagnosis(root):
    from IPython.display import display,Markdown
    s=state(root)
    if s.get('pgvector_concluido'):message='Embeddings e importação no pgvector concluídos e verificados para esta versão.'
    elif s.get('concluido'):message='Embeddings concluídos e validados; consulte a disponibilidade e o estado da importação no pgvector.'
    elif s.get('progresso'):message='Vetorização parcial em andamento ou retomável; ainda não é coleção completa.'
    else:message='Etapa preparada. A geração integral não começou, pois depende do término validado do notebook 05 e da definição do recurso computacional.'
    display(Markdown('**Diagnóstico:** '+message))
    display(Markdown('**Escopo:** vetores densos BGE-M3, normalizados e vinculados por ID/hash/posição ao texto protegido de cada chunk. Índices aproximados, recuperação conjunta com legislação, RRF, reranker e avaliação de respostas permanecem fora desta etapa.'))
