# Preservação das edições dos notebooks de jurisprudência

A pessoa usuária corrigiu os textos Markdown dos notebooks e pediu que suas versões atuais sejam preservadas em futuras atualizações.

- As células Markdown dos notebooks existentes são a referência editorial: preserve seus textos, títulos, metadados, ordem e células acrescentadas ou removidas pela pessoa usuária.
- Não regenere esses textos a partir dos modelos Python antigos. Atualizações de código, resultados ou dados não autorizam restaurar o Markdown dos geradores.
- Use `src.jurisprudencia.notebook_preservation.save_notebook` para salvar atualizações geradas. O modo `generation` atualiza código existente; `execution` atualiza saídas compatíveis. Ambos preservam o Markdown atual e a organização do arquivo.
- Novas células de uma tarefa explicitamente solicitada podem ser inseridas deliberadamente, mantendo os textos já corrigidos. Na API de preservação, autorize somente os IDs dessas células por `allow_new_cell_ids`. Alterações de Markdown diretamente solicitadas pela pessoa usuária continuam autorizadas dentro desse escopo.
- Preserve cópias antes de mudanças: `scripts/preservar_notebooks_jurisprudencia.py`. As cópias integrais e os manifestos SHA-256 ficam em `reports/jurisprudencia/versoes_notebooks/`.
- A versão mais recente salva no arquivo continua sendo a referência, mesmo quando existir uma cópia anterior. Não restaure um backup sem que essa restauração faça parte da solicitação.
- Um pedido apenas de preservação não requer reexecutar, reformatar ou regravar os notebooks. Verifique que seus hashes permaneçam inalterados.

## Organização atual

- Há seis notebooks: 01 (auditoria), 02 (EDA), 03 (limpeza, estruturação e verificação automática), 04 (experimentos de chunking), 05 (chunking definitivo da base consolidada) e 06 (embeddings e indexação).
- O notebook `06_embeddings_indexacao_jurisprudencia.ipynb` exige o corpus integral validado do 05 e a escolha do recurso em `politica_execucao.json` antes da geração em escala. Preserve a distinção entre pré-flight, cache parcial, embeddings completos e coleção pgvector validada. Não altere tabelas ou caches de legislação e não contrate recursos externos automaticamente.
- O notebook `05_chunking_definitivo_jurisprudencia.ipynb` aplica a janela escolhida de 500 tokens com 100 de sobreposição. Preserve seus textos e a distinção entre execução parcial por lotes e corpus integral validado. Não declare a base pronta para embeddings sem `concluido.json` com estado `chunking_validado`; não inicie um segundo escritor ao atualizar o painel.
- Fontes e proveniência e verificações automáticas são seções do notebook 03. A documentação deve apontar diretamente para essas seções.
- Não acrescente referências editoriais a notebooks descontinuados. Preserve os textos atuais nas atualizações dos geradores.
- O notebook `04_experimentos_chunking_jurisprudencia.ipynb` contém experimentos de chunking atuais. Preserve também suas células Markdown nas atualizações de código ou resultados.
- O protocolo de chunking usa seis estratégias, seed fixa, corpus versionado e execução padrão apenas de ajuste. Preserve a reserva de teste e os marcadores de congelamento/início; não apague registros para repetir o teste final.
- Suporte e bootstrap reais exigem evidências vinculadas por documento, intervalo e hash. Sem gabarito, mantenha as métricas indefinidas. Não use scores BM25, exemplos fictícios ou perguntas de legislação como substitutos.
- A métrica principal é Cobertura@T, com T=500/1.000/2.500/5.000 e resumo pela cobertura média em T=2.500. Top 5 é secundário. Não pule um primeiro trecho longo: limite o contexto por prefixo e registre o corte. Preserve a distinção entre fragmentação, evidências separadas e truncamento simulado/real.
