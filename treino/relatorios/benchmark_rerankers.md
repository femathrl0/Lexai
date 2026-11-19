# Benchmark dos rerankers — legislação

Gerado por `python -m treino.benchmark_rerankers` em 2026-11-19T10:56:30 · commit `4ae9b1407f41`.

- **Relevância:** provisória: referências aprovadas de legislação = 2, demais candidatos = 0.
- **Corpus:** 5127 artigos (estratégia A) · perguntas (com e sem resposta): dev 11, teste 9.
- **Candidatos por pergunta:** top-20 denso (BGE-M3) ∪ top-20 palavra-chave, RRF, primeiros 30. Teto (recall do conjunto): dev 1.00, teste 1.00.
- **Escolha no dev (nDCG@5, desempate MRR):** `reranker:BAAI/bge-reranker-v2-m3`.

## Desenvolvimento (escolha)

| Configuração | nDCG@3 | nDCG@5 | nDCG@10 | Recall@1 | Recall@3 | Recall@5 | MRR@10 |
|---|---:|---:|---:|---:|---:|---:|---:|
| sem_reranker:palavra_chave | 0.435 | 0.464 | 0.538 | 0.111 | 0.611 | 0.667 | 0.421 |
| sem_reranker:denso | 0.877 | 0.877 | 0.877 | 0.611 | 1.000 | 1.000 | 0.833 |
| sem_reranker:hibrido_rrf | 0.778 | 0.826 | 0.865 | 0.722 | 0.778 | 0.889 | 0.824 |
| reranker:BAAI/bge-reranker-v2-m3 | 0.959 | 0.959 | 0.959 | 0.833 | 1.000 | 1.000 | 0.944 |

## Teste congelado (só medida)

| Configuração | nDCG@3 | nDCG@5 | nDCG@10 | Recall@1 | Recall@3 | Recall@5 | MRR@10 |
|---|---:|---:|---:|---:|---:|---:|---:|
| sem_reranker:palavra_chave | 0.357 | 0.419 | 0.464 | 0.286 | 0.429 | 0.571 | 0.387 |
| sem_reranker:denso | 0.947 | 0.947 | 0.947 | 0.786 | 1.000 | 1.000 | 0.929 |
| sem_reranker:hibrido_rrf | 0.912 | 0.950 | 0.950 | 0.857 | 0.929 | 1.000 | 0.929 |
| reranker:BAAI/bge-reranker-v2-m3 | 0.956 | 0.956 | 0.956 | 0.857 | 1.000 | 1.000 | 0.929 |

## Custo e separação de perguntas sem resposta

| Reranker | Carga (s) | Latência p50 por pergunta (s) | AUC nota top-1 (com × sem resposta) |
|---|---:|---:|---:|
| reranker:BAAI/bge-reranker-v2-m3 | 3.0 | 5.31 | 1.00 |
