# Model cards

Um card por modelo **em uso** e por candidato relevante (manual: "model card por versão"; issue #38). O que está em
uso é o que `worker/modelos/em_uso.yml` fixa (ou o alias `em-uso` no MLflow, que tem precedência); a referência do
portão de regressão de cada um está em `treino/portoes/linha_base.json`. Modelo: [MODELO.md](MODELO.md).

| Modelo | Em uso | Card | Candidato em avaliação |
|---|---|---|---|
| Tipo de documento e fase | regras do cabeçalho | [classificador_tipo_fase_v1.md](classificador_tipo_fase_v1.md) | TF-IDF + LR v1 (rótulo provisório); BERTimbau + LoRA (`treino/lora_tipo.py`, roda no M4) |
| Segmentador | regras de marcadores (sentença e acórdão) | [segmentador.md](segmentador.md) | TF-IDF + LR com posição (sem títulos) |
| Extrator de campos | regras | [extrator_campos.md](extrator_campos.md) | — (aguarda o 2º lote anotado, #15) |
| Resultado (recurso e pedido) | regras | [resultado_pedido.md](resultado_pedido.md) | TF-IDF de caracteres com aumento de ruído (OCR) |
| Intenção da guarda de entrada | regras (`guardas.verificar_entrada`) | [intencao_guarda.md](intencao_guarda.md) | — (TF-IDF de caracteres não venceu) |
| Reranker | `BAAI/bge-reranker-v2-m3` | [reranker.md](reranker.md) | `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` (mais leve) |
| Verificador NLI | `MoritzLaurer/mDeBERTa-v3-base-mnli-xnli` + regras de saída | [verificador_nli.md](verificador_nli.md) | `…-xnli-multilingual-nli-2mil7`, `multilingual-MiniLMv2-L6` (`treino/benchmark_nli.py`) |
| Embeddings | `BAAI/bge-m3` | [embeddings.md](embeddings.md) | — |

Nenhum modelo tem aprovação da Curadoria registrada ainda: todos os cards terminam com **pendente**.
