# treino/ — Eng. de ML e MLOps

Todo treino é rastreado no MLflow (`MLFLOW_TRACKING_URI`, padrão `http://127.0.0.1:15000`, serviço `mlflow` do Compose) com a versão dos dados (hash do lote) e o commit do código.
Baseline primeiro (TF-IDF + regressão logística ou regras); BERTimbau + LoRA só entra se vencer na validação ([decisão 0003](../docs/decisoes/0003-baselines-por-tarefa.md)).
Registro com estágios: candidato → aprovado → em uso (alias `em-uso`, lido por `worker/modelos/registro.py`). Os scripts daqui só registram como `candidato`.

| Script | O que faz | Saída |
|---|---|---|
| `python -m treino.teste_congelado` | Portão: o conjunto de teste congelado de legislação não mudou (roda no CI) | código de saída |
| `python -m treino.medir_memoria_latencia` | Memória e latência de cada modelo candidato no M4, todos juntos com a LLM, orçamento do worker | [`relatorios/memoria_latencia_m4.md`](relatorios/memoria_latencia_m4.md), MLflow `orcamento-memoria-worker` |
| `python -m treino.classificador_tipo baixar` / `treinar` | Baseline do tipo de documento e fase: classe majoritária, regras, TF-IDF + LR com e sem cabeçalho | [`relatorios/classificador_tipo_baseline.md`](relatorios/classificador_tipo_baseline.md), MLflow `classificador_tipo_fase` |
| `python -m treino.benchmark_rerankers` | nDCG/recall/MRR dos rerankers candidatos sobre os mesmos candidatos do híbrido (RRF) | [`relatorios/benchmark_rerankers.md`](relatorios/benchmark_rerankers.md), MLflow `benchmark_rerankers`, `avaliacao/pares_ouro/reranker_legislacao_para_anotar.csv` |

Também pelo Makefile: `make teste-congelado`, `make medir-memoria`, `make baseline-tipo`, `make benchmark-rerankers`.

[`ml_test_score.md`](ml_test_score.md) tem a nota inicial do ML Test Score (semana 1); repetir na semana 7.

## Primeira vez

```bash
make up                                   # sobe Postgres, Redis, MLflow e MinIO (precisa do .env)
uv sync --group treino --group worker
ollama pull qwen3:8b                      # LLM usada na medição de memória
python -m treino.classificador_tipo baixar
```

Dados crus ficam em `dados/raw/` (fora do Git). O lote do classificador é público (RepoJus, CC BY 4.0) e é baixado por URL com revisão fixa e hash conferido.
