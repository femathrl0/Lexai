# Model card — embeddings `BAAI/bge-m3` (revisão `5617a9f6`)

- **Estágio:** em uso por fixação; mesmo modelo para o corpus jurídico e para os trechos do usuário (manual).
- **Uso pretendido:** busca densa (1024 dimensões) no buscador local e no pgvector; o vetor dos documentos fica em cache por versão do corpus (`dados/output/cache_buscador_local/`).
- **Métricas:** recuperação densa sozinha no teste congelado de legislação: nDCG@5 0,947, Recall@3 1,00 ([benchmark](../../treino/relatorios/benchmark_rerankers.md)).
- **Memória e latência no M4:** 568 M parâmetros, 3,7 GB; 24 ms por consulta, 8,2 s por lote de 32 trechos.
- **Limitações:** trocar o modelo exige reindexar tudo (índice candidato → regressão jurídica → Curadoria, RNF05).
- **Aprovação da Curadoria:** pendente.
