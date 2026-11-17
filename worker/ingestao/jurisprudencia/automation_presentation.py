"""Painéis da verificação computacional; sem requisitos de validação por pessoa."""
from pathlib import Path
import json

def summary_code(stage):
    base="""from worker.ingestao.jurisprudencia import automatic_review
AUTO_DIR,resumo_auto=automatic_review.load(ROOT_JUR)
assert resumo_auto['registros']==179812
assert audit.hash_file(ROOT_JUR/resumo_auto['indice'])==resumo_auto['indice_sha256']
"""
    if stage=='auditoria':return base+"""display(pd.read_csv(AUTO_DIR/'estrutura_json_serializado_amostra.csv'))
display(pd.read_csv(AUTO_DIR/'amostras_automaticas.csv').groupby(['arquivo_id','estrato']).size().rename('amostras_automaticas').to_frame())
print('Verificações automáticas por esquema e amostra; valores de campos JSON e textos pessoais não são exibidos.')
"""
    if stage=='eda':return base+"""display(pd.read_csv(AUTO_DIR/'cobertura_conteudo.csv'))
display(pd.read_csv(AUTO_DIR/'recorte_tribunais.csv'))
display(pd.read_csv(AUTO_DIR/'tamanho_textos.csv'))
print('Tipo declarado é distinguido do inferido; inferência e triagem temática usam regras em até 8.000 caracteres, sem comprovar mérito jurídico.')
"""
    return base+"""display(pd.Series({k:resumo_auto[k] for k in ['registros','textos_vazios','candidatos_rag_criterios_automaticos','candidatos_consolidados','grupos_copias_textuais_candidatas','ocorrencias_copias_textuais_excedentes','exclusoes_fisicas']},name='verificacao_automatica').to_frame())
display(pd.read_csv(AUTO_DIR/'alertas_automaticos.csv'))
verificacao_pos_pln=json.loads((AUTO_DIR/'verificacao_independente_pos_pln.json').read_text(encoding='utf-8'))
assert verificacao_pos_pln['vinculos_texto_processo_atravessando_splits']==0
display(pd.Series(verificacao_pos_pln,name='particoes_pos_pln').to_frame())
print('Critérios de uso/recorte:',AUTO_DIR/'criterios_uso_recorte.json')
print('Índice de candidatos e relações:',ROOT_JUR/resumo_auto['indice'])
print(resumo_auto['limites'])
"""

def add_panel(nb,stage):
    ident='verificacao_automatica_'+stage
    nb['cells']=[c for c in nb['cells'] if c.get('id') not in (ident,ident+'_texto')]
    titles={'auditoria':'## Verificação automática de estrutura interna e amostras',
        'eda':'### Classificação automática de conteúdo e recorte por regras',
        'estrutura':'## Verificação automática da base tratada, cópias e partições'}
    text=titles[stage]+'''\n\nAs verificações abaixo foram executadas sobre o corpus pós-PLN. O relatório distingue evidência declarada, inferências por regras e alertas computacionais. Os resultados são registrados por métodos automáticos; seu alcance não comprova aprovação jurídica ou anonimização integral.'''
    anchor={'auditoria':'qualidade_texto_jur','eda':'sobreposicoes_texto_eda','estrutura':'conclusao_texto_estrutura'}[stage]
    index=next((i for i,c in enumerate(nb['cells']) if c.get('id')==anchor),len(nb['cells']))
    nb['cells'][index:index]=[dict(cell_type='markdown',id=ident+'_texto',metadata={},source=text.splitlines(keepends=True)),
        dict(cell_type='code',id=ident,metadata={},source=summary_code(stage).splitlines(keepends=True),execution_count=None,outputs=[])]
    return nb

def build_review_notebook(root):
    root=Path(root);cells=[]
    def md(ident,text):cells.append(dict(cell_type='markdown',id=ident,metadata={},source=text.strip().splitlines(keepends=True)))
    def code(ident,text):cells.append(dict(cell_type='code',id=ident,metadata={},source=text.strip().splitlines(keepends=True),execution_count=None,outputs=[]))
    md('intro_revisao','''# 04 — Verificação automática e prontidão da jurisprudência

Consolida critérios de uso/recorte, inferência de conteúdo, amostras automáticas, proveniência, relações entre registros e partições pós-PLN. Todos os resultados são baseados em rotinas executadas e evidências salvas. O fluxo é computacional e registra o alcance dos métodos aplicados.''')
    code('config_revisao',"""from pathlib import Path
import sys,json
import pandas as pd
import matplotlib.pyplot as plt
from IPython.display import display,Markdown
ROOT_JUR=next(p for p in (Path.cwd().resolve(),*Path.cwd().resolve().parents) if (p/'src/jurisprudencia/automatic_review.py').is_file())
if str(ROOT_JUR) not in sys.path:sys.path.insert(0,str(ROOT_JUR))
from worker.ingestao.jurisprudencia import automatic_review,audit
REVIEW_DIR,resumo_auto=automatic_review.load(ROOT_JUR)
assert audit.hash_file(ROOT_JUR/resumo_auto['indice'])==resumo_auto['indice_sha256']
assert resumo_auto['registros']==179812
print('Relatórios automáticos:',REVIEW_DIR)
""")
    md('recorte_texto','''## 1. Uso, recorte e separação dos objetivos

Critérios versionados para RAG trabalhista, proposta de avaliação por grupos e ajuste fino desabilitado. Não se presume que dados adequados para recuperação sejam automaticamente gabaritos de avaliação ou exemplos supervisionados.''')
    code('recorte_auto',"""criterios=json.loads((REVIEW_DIR/'criterios_uso_recorte.json').read_text(encoding='utf-8'))
criterios['automacao']['limite']='Sinais não comprovam integralidade do documento, pertinência jurídica ou anonimização completa. Integrações adicionais têm seu estado técnico documentado.'
display(pd.Series(criterios,name='politica_automatica').to_frame())
display(pd.read_csv(REVIEW_DIR/'recorte_tribunais.csv'))
""")
    md('conteudo_texto','''## 2. Conteúdo declarado e inferido, estrutura e cobertura

O tipo declarado é confrontado com tamanho e marcadores estruturais no prefixo de até 8.000 caracteres. Texto com menos de 500 caracteres rotulado como inteiro teor é sinalizado; isso não prova que seja ementa. Sinais temáticos são lexicais e não classificação semântica exaustiva.

A estrutura interna dos JSONs serializados foi amostrada automaticamente em até 32 registros por campo/arquivo. A cobertura é amostral e os valores internos não são exibidos.''')
    code('conteudo_auto',"""display(pd.read_csv(REVIEW_DIR/'cobertura_conteudo.csv'))
display(pd.read_csv(REVIEW_DIR/'estrutura_json_serializado_amostra.csv'))
display(pd.read_csv(REVIEW_DIR/'tamanho_textos.csv'))
""")
    md('qualidade_texto','''## 3. Diagnóstico automático e amostras

As regras detectam textos curtos, datas ausentes/futuras, cronologia suspeita, rótulos de conteúdo e ausência de correspondência de origem. Amostras de textos curtos, longos e com alertas são selecionadas por IDs estáveis, por arquivo, sem exibir os textos. A comparação antes/depois do PLN mede os marcadores jurídicos monitorados; outros aspectos semânticos não são comprovados por esses testes.''')
    code('qualidade_auto',"""display(pd.read_csv(REVIEW_DIR/'alertas_automaticos.csv'))
amostras_auto=pd.read_csv(REVIEW_DIR/'amostras_automaticas.csv')
display(amostras_auto.groupby(['arquivo_id','estrato']).size().rename('amostras').to_frame())
from worker.ingestao.jurisprudencia import light_nlp
_,pln=light_nlp.load(ROOT_JUR)
display(pd.Series({'amostras_antes_depois':pln['amostras'],'reducoes_marcadores_monitorados':pln['indicadores']['amostras_com_marcadores_juridicos_reduzidos_revisar'],'registros_csv_relidos':pln['validacao_csv']['registros_csv_relidos'],'residuos_padrao_cpf':pln['validacao_csv']['residuos_padrao_cpf']},name='checagem_automatica_pln').to_frame())
""")
    md('relacoes_texto','''## 4. Cópias candidatas, proveniências e partições pós-PLN

Os registros e suas origens são preservados. Uma chave estrita de cópia textual candidata combina texto idêntico, tribunal, processo reconhecido, data e tipo declarado; isso não comprova identidade do acórdão. O índice indica representante candidato sem apagar os demais registros. Grupos por texto principal idêntico e processo sintático são recalculados sobre a versão pós-PLN, com proposta de treino/validação/teste por componente.

A checagem independente percorre todas as chaves conhecidas de texto e processo. Zero vínculos atravessando splits não cobre relações semânticas ou identidades processuais não reconhecidas.''')
    code('relacoes_auto',"""display(pd.Series({k:resumo_auto[k] for k in ['registros','grupos_copias_textuais_candidatas','ocorrencias_copias_textuais_excedentes','candidatos_consolidados','componentes_avaliacao','splits_propostos','exclusoes_fisicas']},name='relacoes_pos_pln').to_frame())
checagem=json.loads((REVIEW_DIR/'verificacao_independente_pos_pln.json').read_text(encoding='utf-8'))
assert checagem['vinculos_texto_processo_atravessando_splits']==0
display(pd.Series(checagem,name='checagem_independente').to_frame())
""")
    md('fontes_texto','''## 5. Proveniência e consulta automatizada de fontes oficiais

As correspondências de origem por hash e tamanho são documentadas no notebook 05. Uma amostra de URLs públicas HTTPS em domínios judiciais foi consultada automaticamente. HTTP 200 comprova disponibilidade naquele momento; 403/405 e falhas são registrados. Este módulo não compara integralmente o conteúdo do documento remoto com o local e não declara equivalência documental.''')
    code('fontes_auto',"""fontes_auto=json.loads((REVIEW_DIR/'fontes_oficiais_verificadas.json').read_text(encoding='utf-8'))
display(pd.DataFrame(fontes_auto['resultados']))
print(fontes_auto['limite'])
""")
    md('conclusao_texto','''## 6. Veredicto automático e integração

Preparação técnica e verificações automáticas executadas. O índice contém candidatos segundo a política versionada, alertas e vínculos; ele não é uma aprovação jurídica nem anonimização integral. Os textos com CPFs mascarados permanecem nos shards pós-PLN, separados dos originais.

Não houve indexação, publicação externa, treinamento ou avaliação de respostas de um modelo. Comparação documental integral com fonte oficial, classificação semântica mais abrangente e avaliação com gabaritos são integrações adicionais não implementadas neste módulo.''')
    code('conclusao_auto',"""display(pd.Series({k:v for k,v in resumo_auto.items() if not isinstance(v,dict)},name='resultado_automatico').to_frame())
print('Índice automatizado:',ROOT_JUR/resumo_auto['indice'])
print('Política:',REVIEW_DIR/'criterios_uso_recorte.json')
""")
    nb=dict(cells=cells,metadata={'kernelspec':{'display_name':'Python (.venv lex_clt.ai)','language':'python','name':'lex-clt-ai'},'language_info':{'name':'python'}},nbformat=4,nbformat_minor=5)
    from .notebook_integration import redirect_generated
    if redirect_generated(root,'04_revisao_prontidao_jurisprudencia.ipynb',nb):return
    path=root/'notebooks/02_jurisprudencia/04_revisao_prontidao_jurisprudencia.ipynb'
    from .notebook_preservation import save_notebook
    save_notebook(path,nb)

def update_sources_notebook(root):
    from .notebook_integration import load_state,TARGET,PREFIXES
    root=Path(root)
    if load_state(root):
        # Os textos integrados são autoritativos; não reconstruir o notebook arquivado.
        return
    path=root/'notebooks/02_jurisprudencia/05_origens_recuperacao_jurisprudencia.ipynb'
    nb=json.loads(path.read_text(encoding='utf-8'))
    nb['metadata']['kernelspec']=dict(display_name='Python (.venv lex_clt.ai)',language='python',name='lex-clt-ai')
    for c in nb['cells']:
        if c.get('id')=='conclusao_origens':
            c['source']='''## 3. Proveniência e verificações automatizadas

Estão confirmadas por hash e tamanho as origens de 18 dos 20 arquivos recebidos, equivalentes a 18 dos 19 arquivos ativos. O arquivo ilegível permanece apenas no histórico. O JSON TST ativo não teve correspondência exata e recebe alerta de proveniência; isso não é preenchido por suposição.

O notebook 04 contém critérios de recorte, inferência de conteúdo, amostras computacionais e partições pós-PLN. A consulta de URLs oficiais abaixo mede disponibilidade HTTP; não compara o texto integral remoto com o local. A comparação documental integral é uma integração adicional não implementada.

Os 6.926 registros do STF com sinais de tema trabalhista integram a base atual, junto com TST e TRTs, sem separação. O escopo ativo continua em 179.812 registros. Nenhum registro foi publicado externamente ou indexado automaticamente.
'''.splitlines(keepends=True)
    nb['cells']=[c for c in nb['cells'] if c.get('id') not in ('fontes_oficiais_texto_origens','fontes_oficiais_auto_origens')]
    index=next(i for i,c in enumerate(nb['cells']) if c.get('id')=='conclusao_origens')
    text='''## Consulta automática de URLs oficiais

A amostra consulta somente URLs públicas HTTPS em domínios judiciais, com redirecionamentos restritos. O relatório distingue HTTP 200, bloqueios/respostas e erros. Não expõe o caminho completo ou parâmetros das URLs e não declara equivalência documental pelo status HTTP.'''
    code="""from worker.ingestao.jurisprudencia import automatic_review
AUTO_DIR,resumo_auto=automatic_review.load(ROOT_JUR)
consulta_fontes=json.loads((AUTO_DIR/'fontes_oficiais_verificadas.json').read_text(encoding='utf-8'))
display(pd.DataFrame(consulta_fontes['resultados']))
print(consulta_fontes['limite'])
"""
    nb['cells'][index:index]=[dict(cell_type='markdown',id='fontes_oficiais_texto_origens',metadata={},source=text.splitlines(keepends=True)),
        dict(cell_type='code',id='fontes_oficiais_auto_origens',metadata={},source=code.splitlines(keepends=True),execution_count=None,outputs=[])]
    from .notebook_preservation import save_notebook
    save_notebook(path,nb)
