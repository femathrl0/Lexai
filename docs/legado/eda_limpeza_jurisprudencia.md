# EDA, limpeza e estruturação de jurisprudência

Os notebooks `02_eda_jurisprudencia.ipynb` e `03_limpeza_estruturacao_jurisprudencia.ipynb` ficam em `notebooks/02_jurisprudencia/`. O 02 explora os agregados integrais da auditoria; o 03 apresenta a base canônica criada por leitura em lotes das fontes legíveis.

Os notebooks 01–03 usam o kernel `Python (.venv lex_clt.ai)` e apresentam 19 arquivos ativos, com 609.872 registros e 18 origens confirmadas por hash/tamanho. A origem individual do JSON TST continua pendente. O arquivo ilegível foi excluído do escopo ativo, preservando o inventário histórico dos 20 arquivos recebidos. A EDA inclui tabela e gráfico de triagem temática por metadados, sem classificação jurídica do conteúdo. A cópia adicional de 50.000 registros STF permanece separada dos 609.872 registros originais. As conclusões atuais são salvas como `conclusao_auditoria_atualizada.md`, `conclusao_eda_atualizada.md` e `conclusao_estrutura_atualizada.md` nos relatórios de cada etapa.

O notebook 03 distingue a base canônica original da derivada CSV/Parquet com CPFs mascarados. Ele exibe as contagens da proteção e verifica o hash do CSV completo; essa célula lê aproximadamente 13 GB e informa o início/fim da verificação. O histórico de quarentena não é apresentado como pendência de reenvio no escopo ativo. Repetições e partições anteriores ao mascaramento ainda precisam ser reavaliadas na versão protegida antes de um experimento.

Para sincronizar a narrativa novamente, execute `scripts/atualizar_apresentacao_jurisprudencia.py`, seguido de `scripts/run_auditoria_jurisprudencia.py` e de `scripts/run_preparacao_jurisprudencia.py --etapa eda` / `--etapa estrutura`, usando o Python da `.venv`. Essa atualização lê os resultados salvos; não reprocessa as fontes brutas.

## Executar

```powershell
.\.venv\Scripts\python.exe scripts/preparar_jurisprudencia.py --etapa todas
.\.venv\Scripts\python.exe scripts/run_preparacao_jurisprudencia.py --etapa todas
```

O primeiro comando executa as transformações, com checkpoints por arquivo e validação de hashes. O segundo preenche os notebooks com tabelas e gráficos dos resultados salvos, sem reler as origens. Cada etapa também pode ser executada separadamente com `--etapa eda` ou `--etapa estrutura`. As opções de execução pesada ficam desativadas nos notebooks por padrão.

## EDA inicial

Saídas em `reports/jurisprudencia/eda/`, identificadas por inventário e código. Incluem composição por tribunal, distribuição temporal, tamanhos, ausências lógicas, categorias top 30 por campo/arquivo, gráficos e conclusão. A média global de tamanho é ponderada por registros; quantis globais não são obtidos pela média dos quantis de arquivos. Os agregados não autorizam inferir uma distribuição conjunta tribunal × ano não medida nem pertinência temática do STF.

## Base estruturada

`data/processed/jurisprudencia/estrutura_ativa.json` aponta para os dados canônicos e relatórios. Cada shard representa um arquivo integralmente auditado, com o mesmo número de registros. O arquivo ilegível fica registrado em um manifesto de quarentena; o original não é movido nem reparado silenciosamente. Uma mudança de hash nas fontes interrompe a estruturação e exige nova auditoria.

O texto original selecionado e a ementa original ficam preservados em colunas separadas das versões limpas. Há IDs determinísticos, arquivo/linha, hashes de origem e registro, metadados canônicos, datas separadas, operações e motivos de revisão. Campos fora do esquema permanecem recuperáveis na origem pela linhagem; não se afirma que JSONs embutidos em strings tenham sido totalmente expandidos.

`linha_origem` corresponde à linha física no JSONL e ao índice do registro, começando em 1, no JSON em array e no Parquet. O índice auxiliar `grupos_processuais.parquet` agrupa CNJ sintático entre tribunais, sem incluir o tribunal julgador na chave; números antigos conservam namespace do tribunal e exigem revisão. Não há validação de dígitos verificadores, garantia de identidade jurídica nem criação automática de splits.

A limpeza trata apresentação HTML, Unicode NFC, BOM, espaços e quebras de linha. Não remove stopwords, negações ou dispositivos legais e não faz reescrita jurídica. Transformações de HTML e codificação exigem conferência; a preservação do original permite essa comparação. Quando o texto muda, offsets originais não são reutilizados sem um mapa de alinhamento; esse mapa não foi produzido nesta etapa.

Não há exclusão automática por texto, processo ou chave documental. `sinais_repeticao.parquet` é um índice lateral para join por `registro_id`; não é um shard adicional de decisões. Para ler o corpus sem somar o índice lateral:

```python
from pathlib import Path
from src.jurisprudencia.dataset import open_dataset
corpus = open_dataset(Path.cwd())
print(corpus.count_rows())
```

Evite ler indiscriminadamente todos os Parquet da pasta como se tivessem o mesmo papel. Os relatórios ficam em `reports/jurisprudencia/estruturacao/`; o índice temporário de fingerprints fica em `tmp/jurisprudencia_estrutura/` e não deve ser publicado.

Execute o exemplo de leitura na raiz do projeto. Dentro dos notebooks, utilize `ROOT_JUR`, já resolvido automaticamente, em vez de presumir que o diretório corrente seja a raiz.

## Resultado da execução

A execução preservou 609.872 registros dos 19 arquivos legíveis, reconciliados com a auditoria, sem exclusões automáticas. Um arquivo de leitura problemática ficou registrado no manifesto de quarentena, sem estimativa de seu número de registros. A apresentação textual mudou em 186.311 registros, mantendo as versões originais. Foram identificados 1.602 grupos de texto limpo repetido, com 13.607 ocorrências excedentes; essas ocorrências permanecem na base e não constituem, por si só, duplicatas jurídicas.

Os notebooks incluem tabelas, gráficos e conclusões dos resultados efetivamente processados. A suíte do projeto passou com 93 testes, incluindo os testes do mascaramento de CPFs. A contagem de 608.183 candidatos técnicos não representa liberação para indexação: ela não aprova privacidade, licença ou pertinência jurídica.

## Limites de uso

A base canônica original não é anonimizada. A seção **Proteção de dados pessoais** do notebook 03 gera uma derivada separada em CSV e Parquet com CPFs mascarados; ver [regras e limitações](protecao_cpf_jurisprudencia.md). O mascaramento não cobre todos os dados pessoais nem libera automaticamente a publicação. Sinais de CPF/e-mail são triagem do texto original selecionado, não garantia de ausência de dados pessoais. “Candidato técnico de indexação” não aprova privacidade, licença, pertinência temática ou correção jurídica. Origem por hash/tamanho e licença declarada estão registradas para 18 de 20 arquivos; `jurisprudencias_tst.json` e o `train-00002.parquet` local com erro ainda não têm correspondência exata. Não houve publicação, treinamento, geração de embeddings ou alteração do RAG legislativo.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
