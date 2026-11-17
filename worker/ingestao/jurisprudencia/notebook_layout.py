"""Sequência didática de títulos da EDA, sem alterar as transformações executadas."""

def eda_layout(nb):
    code={c['id']:c for c in nb['cells'] if c['cell_type']=='code'}
    intro=next(c for c in nb['cells'] if c.get('id')=='intro_eda')
    cells=[intro]
    def md(ident,text):
        cells.append(dict(cell_type='markdown',id=ident,metadata={},source=text.strip().splitlines(keepends=True)))
    def run(ident):cells.append(code[ident])

    md('bibliotecas_texto_eda','''## 1. Importação de bibliotecas e configuração do ambiente

Importação de bibliotecas, localização da raiz do projeto e leitura dos relatórios já calculados. Use o kernel **Python (.venv lex_clt.ai)**. `EXECUTAR_EDA=False` mantém a leitura dos resultados salvos; a integridade dos agregados de origem é conferida por hash.''')
    run('config_eda')
    md('importacao_escopo_texto_eda','''## 2. Importação dos dados e definição do escopo

Carregamento do contexto e dos manifestos das etapas anteriores e posteriores. A EDA usa os agregados dos **19 arquivos ativos**, com 179.812 registros legíveis. Os 6.926 registros do STF com sinais de tema trabalhista integram a base atual, junto com TST e TRTs, sem separação.''')
    run('situacao_atual_eda')
    md('limpeza_estrutural_texto_eda','''## 3. Limpeza estrutural e unificação dos textos

**Executada no notebook 03; aqui é documentada para orientar a leitura do fluxo.** A estruturação padronizou campos e tipos, associou tribunal, processo, datas e origem e selecionou o texto principal disponível, distinguindo inteiro teor, ementa e texto de busca.

A unificação significa um esquema comum por registro, com linhagem. Não concatena decisões diferentes nem transforma uma ementa em inteiro teor. As versões originais continuam separadas e as diferenças entre julgamento, publicação e assinatura são preservadas.''')
    from .pln_presentation import DESCRIPTION,result_code
    md('normalizacao_conservadora_texto_eda','## 4. Limpeza leve e normalização conservadora, preservando o texto jurídico (PLN)\n\n'
       +'**Executada na etapa de limpeza do notebook 03; os resultados auditados são carregados abaixo.**\n\n'+DESCRIPTION)
    cells.append(dict(cell_type='code',id='pln_resultado_eda',metadata={},source=result_code().splitlines(keepends=True),execution_count=None,outputs=[]))
    md('eda_principal_texto_eda','''## 5. Análise exploratória de dados (EDA)

Exploração descritiva de composição por tribunal, tamanhos, cobertura temporal, completude, categorias declaradas e repetições. As proporções usam os registros legíveis, incluindo possíveis sobreposições. Os achados descrevem os arquivos disponíveis; não comprovam representatividade das demandas trabalhistas.''')
    md('composicao_texto_eda','''### 5.1. Composição, volume e tribunais utilizados

Distribuição por tribunal e inventário dos 19 arquivos ativos. O arquivo ilegível consta apenas no histórico. As contagens não representam necessariamente decisões jurídicas únicas.''')
    run('composicao_eda')
    md('texto_datas_texto_eda','''### 5.2. Tamanho dos textos e cobertura temporal

Os tamanhos estão em caracteres, não tokens. A média global é ponderada; medianas e p95 permanecem por arquivo, sem calcular quantis globais pela média dos quantis locais. O ano pode ser de julgamento ou assinatura, conforme o campo disponível, sem equiparar as duas datas.''')
    run('texto_datas_eda')
    md('categorias_texto_eda','''### 5.3. Completude, classes e tipos declarados

Ausências lógicas consideram os campos alternativos disponíveis; não se somam ausências de colunas como se fossem documentos diferentes. As categorias são top 30 por campo/arquivo, sem harmonização jurídica. Não permitem deduzir uma distribuição conjunta tribunal × ano não medida.''')
    run('categorias_eda')
    md('tema_texto_eda','''### 5.4. Triagem temática por metadados e pertinência trabalhista

Jurisdição trabalhista e ramo declarado são evidências para revisão. A simples presença de um documento STF ou de palavras jurídicas não confirma pertinência ao RAG trabalhista. Esta triagem não é classificação semântica do conteúdo.''')
    run('tema_atual_eda')
    md('sobreposicoes_texto_eda','''### 5.5. Sobreposições, repetições e preparação da avaliação

Registro integralmente idêntico, texto igual, chave documental candidata e mesmo processo são critérios diferentes e sobrepostos. Um processo pode conter várias decisões legítimas. A tabela histórica é preservada; os vínculos e as partições da versão pós-PLN foram recalculados no painel automático.''')
    run('sobreposicoes_eda')
    md('graficos_texto_eda','''### 5.6. Gráficos e visualização dos resultados da EDA

Os gráficos descrevem os 179.812 registros do escopo ativo, antes do mascaramento. As barras de ausência e os sinais técnicos não são notas de correção jurídica. Os gráficos incluem os 6.926 registros do STF da base atual, junto com TST e TRTs.''')
    run('graficos_eda')
    md('salvando_dataset_texto_eda','''## 6. SALVANDO O DATASET LIMPO E TRATADO

**Exportação executada no notebook 03.** Foram gerados CSV UTF-8 e shards Parquet separados, com `texto_protegido`, `ementa_protegida` e metadados selecionados. As colunas de texto original não entram nessa derivada.

Este notebook lê os relatórios, sem regravar os dados. A derivada inicial de CPF está em `data/processed/jurisprudencia/protecao_cpf/ativa.json`. A versão após PLN leve está em `data/processed/jurisprudencia/pln_leve/ativa.json`, com `ementa`, `inteiro_teor`, `texto_busca` e variantes identificadas, sem promover ementa a inteiro teor. O CSV após PLN também foi relido integralmente. Os originais e as versões anteriores continuam preservados separadamente.''')
    md('validacao_protecao_texto_eda','''### 6.1. Proteção de dados pessoais e validação da exportação

Verificação das contagens e do resultado documentado da releitura do CSV protegido. As substituições são ocorrências nos campos tratados, não CPFs distintos ou número de pessoas. Outros dados pessoais e formas de ofuscação não cobertas continuam exigindo revisão.''')
    run('privacidade_resultado_eda')
    md('conclusao_texto_eda','''## 7. Análise e avaliação dos resultados

Interpretação dos achados da EDA, da rastreabilidade e da proteção concluída. Trata-se de avaliação descritiva dos dados, não de métricas de desempenho ou de aprovação jurídica de um modelo. A conclusão distingue o que está concluído das revisões ainda necessárias.''')
    run('conclusao_eda')
    md('diagnostico_observacoes_texto_eda','''## 8. Diagnóstico e Observações

- Fontes heterogêneas e concentração por tribunal limitam generalizações.
- Ementa, inteiro teor e texto de busca não são equivalentes; datas de assinatura e julgamento também não.
- A origem de 18 dos 19 arquivos ativos está confirmada; o JSON TST continua pendente.
- O mascaramento de CPFs está concluído na derivada protegida; não elimina a necessidade de revisar outros dados pessoais.
- O painel automático registra inferência de conteúdo, sinais temáticos, cópias candidatas e partições pós-PLN. Os rótulos são heurísticos e sua cobertura é documentada.

Os detalhes das filas e critérios de revisão estão no [notebook 04](04_revisao_prontidao_jurisprudencia.ipynb); as evidências de origem e licença declarada estão no [notebook 05](05_origens_recuperacao_jurisprudencia.ipynb).''')
    md('integracao_texto_eda','''## 9. Integração

**Preparação para integração futura.** Uma seleção aprovada deverá partir do texto protegido do [notebook 03](03_limpeza_estruturacao_jurisprudencia.ipynb), preservar os IDs de linhagem e a fonte e calcular offsets na versão textual efetivamente usada. Chunking, embeddings e indexação dependem das revisões restantes.

Os grupos pós-PLN têm checagem independente dos vínculos conhecidos de texto e processo. Este notebook não indexa os dados, não treina modelos e não altera o RAG legislativo existente.''')
    nb['cells']=cells
    if len({c['id'] for c in cells})!=len(cells):raise ValueError('IDs de células repetidos.')
    return nb
