# Experimentos de chunking da jurisprudência

O protocolo atual foi ampliado para seis estratégias, cobertura contínua de evidência, quatro orçamentos de contexto, testes de limites, bootstrap pareado e separação prospectiva ajuste/teste. Veja [Avaliação avançada de chunking](avaliacao_chunking_avancada.md). As três versões abaixo são as bases da comparação; o número de consultas por execução agora depende da partição selecionada, e não corresponde a consultar automaticamente as 30 perguntas.

O [notebook de experimentos](../notebooks/02_jurisprudencia/04_experimentos_chunking_jurisprudencia.ipynb) compara três versões: janela fixa de até 500 tokens sem sobreposição, parágrafo do acórdão e seção/tema com ligação conservadora ao dispositivo. Usa os mesmos documentos protegidos em todas as versões, sem alterar os notebooks de preparação.

O recorte parte de até 120 candidatos consolidados selecionados deterministicamente; para este protocolo são mantidos os que têm `inteiro_teor` como campo principal. A partição documental proposta de teste é excluída da amostra inicial. Documentos esperados por perguntas com evidências são acrescentados às três versões se necessário. A amostra não representa proporcionalmente o corpus nem confirma a integralidade jurídica dos textos rotulados na fonte.

O critério principal é **Hit de suporte@5**: o top 5 deve cobrir integralmente pelo menos um conjunto alternativo de trechos esperados. Documento@5 é secundário. Uma passagem do relatório que apenas menciona horas extras não é acerto de suporte se a referência esperada mostra que o tribunal não conheceu do recurso, sem exame do mérito.

A unidade de parágrafo é inspirada na [tarefa de entailment do COLIEE](https://coliee.org/COLIEE2025/tasks/task2); o corpus brasileiro e a métrica deste projeto são próprios. Parágrafos são aproximados por formatação quando não há identificação oficial. Parágrafos e blocos de seção/tema longos permanecem inteiros, sem truncamento, e seu custo em tokens é registrado.

## Execução

Instale `requirements-chunking-jurisprudencia.txt` no ambiente do projeto. É necessário o tokenizador local de `BAAI/bge-m3`; não há download automático. O recuperador comum às três versões é BM25 lexical (`k1=1,2`, `b=0,75`), sem embeddings ou reranking. Execute o notebook em ordem ou:

```powershell
.\.venv\Scripts\python.exe scripts/run_chunking_jurisprudencia.py
```

Os experimentos verificam o SHA-256 dos shards protegidos e do índice automático, os offsets exatos, a cobertura de caracteres, os limites de tokens, IDs únicos e a integridade da exportação relida. Textos reais não são exibidos. O mascaramento de CPF não constitui anonimização integral.

## Resultados

`reports/jurisprudencia/chunking_suporte/ativa.json` aponta para a execução completa. Chunks protegidos ficam em `data/chunks/jurisprudencia/suporte/`, ignorada pelo Git. Relatórios e rankings contêm IDs, offsets e contagens, sem texto real ou número de processo. O notebook exibe texto somente nos controles fictícios.

O dispositivo é vinculado somente à fundamentação/voto com correspondência temática unívoca. Dispositivo genérico ou ambíguo fica sem ligação. A expansão é medida separadamente dos cinco resultados diretos, e não é prova automática de entailment.

As 30 perguntas do CSV fornecido são carregadas por `data/evaluation/jurisprudencia/perguntas_ativas.json`. O protocolo atual separa 23 para ajuste e 7 para teste final e avalia seis estratégias no ajuste, sem consultar automaticamente as reservadas. O conjunto de legislação não é utilizado. O original é preservado por SHA-256; a entrada é validada sem modificar os enunciados.

As [perguntas com evidências](../data/evaluation/jurisprudencia/README.md) são carregadas de `data/evaluation/jurisprudencia/perguntas_suporte.jsonl` quando disponíveis. O gabarito exige documento, campo, offsets e SHA-256 da referência. Sem essas evidências, a execução apresenta rankings e custo do contexto para todas as consultas, mas não calcula acurácia a partir de scores BM25. As colunas `trechos_esperados` e `resposta_esperada` do CSV recebido estão vazias.

Sem evidências reais, as métricas reais ficam indefinidas, sem atribuir 0% de acerto ou declarar vencedor. Quatro casos autorais fictícios exercitam o avaliador separadamente, incluindo o caso de pedido no relatório e inadmissibilidade do recurso. O acerto deles não estima qualidade no acervo real nem substitui o teste com embeddings.
