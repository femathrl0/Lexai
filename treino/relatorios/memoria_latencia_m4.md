# Memória e latência no MacBook M4 — orçamento do worker

Gerado por `python -m treino.medir_memoria_latencia` em 2026-11-24T15:21:34 · commit `264807194dae` · Apple M4, 24 GB · device `mps`.

## Modelos isolados (um processo por modelo)

| Modelo | Repositório | Parâmetros | Carga (s) | Memória após carga (GB) | Pico (GB) | Latência p50 / p95 (ms) |
|---|---|---:|---:|---:|---:|---|
| embeddings_bge_m3 | `BAAI/bge-m3` | 568 M | 4.8 | 3.70 | 4.90 | consulta_1: 24 / 25; lote_32_trechos: 8237 / 8834 |
| reranker_bge_v2_m3 | `BAAI/bge-reranker-v2-m3` | 568 M | 3.8 | 3.75 | 3.96 | rerank_30_pares: 5284 / 5392 |
| verificador_mdeberta_xnli | `MoritzLaurer/mDeBERTa-v3-base-mnli-xnli` | 279 M | 1.9 | 1.50 | 1.80 | par_1: 133 / 148; resposta_10_frases: 2981 / 3004 |
| classificador_bertimbau_base | `neuralmind/bert-base-portuguese-cased` | 109 M | 1.4 | 1.48 | 1.35 | documento_512_tokens: 60 / 72 |

## LLM (Ollama, nativo)

| Modelo | Quantização | Parâmetros | num_ctx | Memória (GB) | 1º token (ms) | Prefill (tok/s) | Geração (tok/s) |
|---|---|---|---:|---:|---:|---:|---:|
| `qwen3:8b` | Q4_K_M | 8.2B | 16384 | 7.31 | 22205 | 106 | 12.1 |

## Todos juntos (como o worker carrega) + LLM

- Modelos de ML no mesmo processo: **6.49 GB** após carga, **7.36 GB** no pico das cargas típicas.
- LLM no Ollama: **7.31 GB**.
- Memória do sistema no pior momento (tudo carregado): 1.4 GB disponíveis de 24 GB (94% em uso).

| Latência com todos carregados | p50 / p95 (ms) |
|---|---|
| embeddings_bge_m3 · consulta_1 | 24 / 25 |
| embeddings_bge_m3 · lote_32_trechos | 10041 / 10230 |
| reranker_bge_v2_m3 · rerank_30_pares | 5483 / 6713 |
| verificador_mdeberta_xnli · par_1 | 145 / 174 |
| verificador_mdeberta_xnli · resposta_10_frases | 3171 / 3440 |
| classificador_bertimbau_base · documento_512_tokens | 154 / 243 |

## Orçamento de memória do worker

| Item | GB |
|---|---:|
| RAM total | 24.0 |
| Reserva: macOS, Docker (Postgres, Redis, MLflow, MinIO), navegador | 8.0 |
| **Orçamento do worker** | **16.0** |
| LLM (`qwen3:8b`) | 7.31 |
| Modelos de ML juntos (pico) | 7.36 |
| **Worker total** | **14.67** |
| **Folga** | **1.33** |

**Cabe no orçamento: sim.**
