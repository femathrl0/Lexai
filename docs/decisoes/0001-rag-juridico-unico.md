# 0001 — Um RAG jurídico (leis e jurisprudência no mesmo índice)

Data: 17/11/2026

**Contexto.** O desenho anterior tinha dois RAGs, um para leis e outro para jurisprudência (como no lex_clt.ai, que mantém tabelas e recuperações separadas e junta por cotas). Em 7 semanas, cada índice extra é mais um artefato para versionar, regredir e aprovar.

**Decisão.** Um único índice `corpus_juridico` no pgvector, com metadado `tipo_fonte` (lei, súmula, OJ, ementa), fonte, versão e vigência. A distinção entre lei e jurisprudência passa a ser feita por filtro: o recuperador traz candidatos de cada tipo antes do reranker, e a resposta mostra os dois em blocos separados. A recuperação é medida por tipo de fonte.

**Alternativa descartada.** Dois índices separados com fusão posterior — mais controle por fonte, mas o dobro de versões e regressões.
