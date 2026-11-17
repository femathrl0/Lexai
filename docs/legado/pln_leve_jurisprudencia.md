# Limpeza leve e normalização conservadora, preservando o texto jurídico (PLN)

Esta etapa complementa a limpeza do notebook 03 e tem seus resultados auditados apresentados também na seção 4 do notebook 02. Não remove stopwords, acentos, pontuação, negações, exceções ou referências jurídicas.

## Método

| Etapa | Tratamento |
| --- | --- |
| Formatação | Conversão de entidades HTML, inclusive em texto sem tags; extração do HTML reconhecido com limites de parágrafos, títulos e listas; preservação da numeração de listas ordenadas reconhecidas; normalização de espaços. |
| Caracteres | Unicode NFC e quebras de linha padronizadas, mantendo referências como `art. 482`, `§ 2º` e `Súmula 331`. |
| Extração | Detecção de linhas recorrentes de início/fim por fingerprint, sem remoção automática. Detecção limitada a palavras de 2–80 letras partidas por hífen/quebra de linha; identificadores extensos não são tratados como palavras. |
| Auditoria | Textos principais vazios antes/depois, campos ausentes e vazios, duplicatas exatas por texto principal e campos textuais, amostra local antes/depois e verificação automatizada de marcadores jurídicos. |

Os candidatos a cabeçalho/rodapé são linhas de 8–200 caracteres, entre as primeiras/últimas duas linhas do documento, recorrentes em ao menos 10 documentos. Isso não é detecção completa de cabeçalhos de páginas PDF e não prova que uma linha seja dispensável. Textos como títulos e fórmulas jurídicas podem legitimamente se repetir.

Não há origem PDF confirmada para autorizar a união automática de palavras neste lote. A função suporta correção somente com confirmação de PDF e vocabulário aprovado. `pré-judicial` e casos incertos são preservados; candidatos a palavras partidas ficam sinalizados para revisão. Não se inventa um vocabulário de correções.

## Campos e proteção

A entrada é a derivada com CPFs mascarados. A entidade HTML pode codificar dígitos; por isso o mascaramento é reaplicado após decodificar e normalizar os textos. A etapa não representa anonimização completa.

`ementa`, `inteiro_teor` e `texto_busca` são colunas próprias, preenchidas conforme o tipo declarado na fonte. `texto_outro` preserva conteúdo sem tipo reconhecido, e `ementa_alternativa` conserva uma ementa distinta quando a fonte tem mais de uma variante. `texto_principal_campo` identifica a coluna de texto principal. Uma ementa não é promovida a inteiro teor; o tipo declarado não comprova a integralidade jurídica do documento.

A saída não sobrescreve os originais nem as derivadas anteriores. É gerada em Parquet e CSV. `data/processed/jurisprudencia/pln_leve/ativa.json` aponta para a versão concluída; arquivos parciais ou diretórios sem esse vínculo não são uma entrega final. O CSV é relido integralmente para conferir a quantidade e resíduos dos padrões de CPF tratados nos textos.

Não abra indiscriminadamente todos os Parquet da pasta como se fossem documentos: ela também contém a amostra antes/depois. Para selecionar somente os shards do corpus, use `src.jurisprudencia.pln_dataset.open_dataset(ROOT_JUR)`, que lê os arquivos listados no manifesto. A amostra deve ser aberta separadamente para revisão local.

## Resultado da execução

Foram mantidos 609.872 registros, com zero textos principais vazios antes/depois e zero exclusões automáticas. Como a entrada já havia passado pela normalização inicial, houve 15 alterações complementares em campos textuais: 10 conversões de entidades e cinco ajustes de espaços. O CSV final foi integralmente relido, sem resíduos dos padrões de CPF tratados nos campos de texto.

A amostra local tem 55 comparações, sem reduções dos marcadores jurídicos monitorados na checagem automática. O alcance da checagem é limitado aos marcadores documentados. Foram encontrados 1.602 grupos de texto principal exatamente repetido, com 13.607 ocorrências excedentes, preservados na saída. Há 1.537 candidatos recorrentes de início/fim por fingerprint.

A auditoria reconta um sinal amplo de hífen no fim da linha para revisão; esse sinal não prova palavra partida, não confirma origem PDF e não autoriza junção automática. Três campos com entidades residuais e 56 com caracteres Unicode de substituição continuam sinalizados. Não houve correção por suposição.

As saídas já normalizadas foram preservadas após uma interrupção na finalização. A auditoria foi recuperada por comparação integral com a entrada, verificação dos IDs/metadados e revalidação de cada diferença pelas regras de limpeza. Campos idênticos herdam a normalização NFC da entrada canônica. O CSV foi relido e renomeado em processo separado; os manifestos registram o código das regras revalidadas e o verificador de recuperação. Os notebooks 02 e 03 têm, respectivamente, 11 e 10 células executadas sem erros.

## Amostra e verificação automática

`amostra_antes_depois.parquet` contém exemplos reais locais, limitados por campo e condição de alteração. Não é uma amostra probabilística representativa. O antes parte da derivada de CPF; nomes e outros dados pessoais podem continuar presentes. O arquivo permanece em dados processados ignorados pelo Git e não é reproduzido nos notebooks.

A comparação automática conta marcadores como “não”, “salvo” e referências jurídicas; reduções produzem alertas, sem atribuir parecer jurídico. Os notebooks mostram exemplos sintéticos e contagens agregadas. A seção de verificação automática do notebook 03 apresenta inferência de conteúdo, sinais temáticos, amostras por estrato e checagem independente das partições pós-PLN.

## Executar

```powershell
.\.venv\Scripts\python.exe scripts/preprocessar_pln_leve_jurisprudencia.py
.\.venv\Scripts\python.exe scripts/run_preparacao_jurisprudencia.py --etapa estrutura
.\.venv\Scripts\python.exe scripts/run_preparacao_jurisprudencia.py --etapa eda
```

Uma futura seleção para RAG deve partir da versão aprovada após PLN, reavaliar coincidências/partições e calcular offsets nessa versão. Não há indexação, embeddings, treinamento ou classificação temática nesta etapa.
