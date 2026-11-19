# Memória e latência no MacBook M4 — orçamento do worker

Gerado por `python -m treino.medir_memoria_latencia` em 2026-11-19T10:36:06 · commit `4ae9b1407f41` · Apple M4, 24 GB · device `mps`.

## Modelos isolados (um processo por modelo)

| Modelo | Repositório | Parâmetros | Carga (s) | Memória após carga (GB) | Pico (GB) | Latência p50 / p95 (ms) |
|---|---|---:|---:|---:|---:|---|
| embeddings_bge_m3 | `BAAI/bge-m3` | 568 M | 4.6 | 3.17 | 4.44 | consulta_1: 23 / 25; lote_32_trechos: 6036 / 6234 |
| reranker_bge_v2_m3 | `BAAI/bge-reranker-v2-m3` | 568 M | 4.9 | 3.75 | 3.96 | rerank_30_pares: 3532 / 3605 |
| verificador_mdeberta_xnli | `MoritzLaurer/mDeBERTa-v3-base-mnli-xnli` | 279 M | 2.1 | 1.50 | 1.80 | par_1: 112 / 114; resposta_10_frases: 1850 / 1973 |
| classificador_bertimbau_base | `neuralmind/bert-base-portuguese-cased` | 109 M | 1.5 | 1.48 | 1.35 | documento_512_tokens: 50 / 52 |

## LLM (Ollama, nativo)

| Modelo | Quantização | Parâmetros | num_ctx | Memória (GB) | 1º token (ms) | Prefill (tok/s) | Geração (tok/s) |
|---|---|---|---:|---:|---:|---:|---:|
| `qwen3:8b` | Q4_K_M | 8.2B | 8192 | 5.51 | 174 | 36830 | 15.8 |

## Todos juntos (como o worker carrega) + LLM

- Modelos de ML no mesmo processo: **6.22 GB** após carga, **7.74 GB** no pico das cargas típicas.
- LLM no Ollama: **5.51 GB**.
- Memória do sistema no pior momento (tudo carregado): 2.0 GB disponíveis de 24 GB (92% em uso).

| Latência com todos carregados | p50 / p95 (ms) |
|---|---|
| embeddings_bge_m3 · consulta_1 | 23 / 24 |
| embeddings_bge_m3 · lote_32_trechos | 7879 / 8050 |
| reranker_bge_v2_m3 · rerank_30_pares | 4567 / 4707 |
| verificador_mdeberta_xnli · par_1 | 126 / 143 |
| verificador_mdeberta_xnli · resposta_10_frases | 2463 / 2675 |
| classificador_bertimbau_base · documento_512_tokens | 61 / 64 |

## Orçamento de memória do worker

| Item | GB |
|---|---:|
| RAM total | 24.0 |
| Reserva: macOS, Docker (Postgres, Redis, MLflow, MinIO), backend, navegador | 8.0 |
| **Orçamento do worker** | **16.0** |
| LLM (`qwen3:8b`) | 5.51 |
| Modelos de ML juntos (pico) | 7.74 |
| **Worker total** | **13.25** |
| **Folga** | **2.75** |

**Cabe no orçamento: sim.**
