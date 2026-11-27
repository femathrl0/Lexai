COMPOSE = docker compose -f infra/docker-compose.yml --env-file .env

.PHONY: setup up down migrar backend worker frontend test lint preparar-modelos \
	test-integracao cobertura tipos esquemas pipeline pre-commit \
	teste-congelado medir-memoria baseline-tipo benchmark-rerankers \
	portao-regressao lora-tipo lora-tipo-amostra benchmark-nli segmentador resultado-pedido configuracoes \
	extrator-campos intencao registrar-cross-encoders ruido-ocr deriva aprendizado-ativo

setup:            ## instala dependências (backend + dev)
	uv sync
up:               ## sobe Postgres, Redis, MLflow e MinIO
	$(COMPOSE) up -d
down:
	$(COMPOSE) down
migrar:
	uv run alembic upgrade head
backend:
	uv run uvicorn backend.main:app --reload
worker:           ## nativo no macOS (usa a GPU do M4)
	uv run --group worker python -m worker.main
frontend:
	cd frontend && npm install && npm run dev
test:
	uv run pytest -q -m "not integracao"
test-integracao:  ## com os serviços do Compose no ar (make up)
	uv run pytest -q -m integracao tests/integracao
cobertura:
	uv run pytest -q -m "not integracao" --cov --cov-report=term --cov-report=html
tipos:
	uv run mypy
esquemas:         ## valida os dados versionados (e o lote RepoJus, se baixado) com Pandera
	uv run --group treino python -m treino.esquemas
pipeline:         ## refaz só os estágios do dvc.yaml cujo código, dados ou parâmetros mudaram
	uv run --group treino dvc repro
pre-commit:
	uv run pre-commit install
lint:
	uv run ruff check .
preparar-modelos: ## baixa LLM quantizada, embeddings e cross-encoders
	./scripts/preparar_modelos.sh

# Eng. de ML e MLOps (treino/). Registram no MLflow do Compose (make up).
teste-congelado:  ## portão: o conjunto de teste congelado não mudou
	uv run python -m treino.teste_congelado
medir-memoria:    ## memória e latência dos modelos no M4 + orçamento do worker (Ollama aberto)
	uv run --group worker --group treino python -m treino.medir_memoria_latencia
baseline-tipo:    ## baseline TF-IDF + LR do tipo de documento e fase
	uv run --group treino python -m treino.classificador_tipo treinar
benchmark-rerankers: ## nDCG dos rerankers candidatos nos pares de legislação
	uv run --group worker --group treino python -m treino.benchmark_rerankers
portao-regressao: ## portão: nenhum modelo piorou em métrica principal nem em erro grave
	uv run python -m treino.portao_regressao
lora-tipo:        ## BERTimbau + LoRA contra o baseline (rodada completa, M4/MPS)
	uv run --group treino python -m treino.lora_tipo
lora-tipo-amostra: ## fumaça do LoRA na CPU (200 por divisão, não registra)
	uv run --group treino python -m treino.lora_tipo --amostra 200 --epocas 1 --max-tokens 256
benchmark-nli:    ## verificadores NLI candidatos nos pares-ouro (M4: DEVICE=mps)
	uv run --group worker --group treino python -m treino.benchmark_nli $(if $(DEVICE),--device $(DEVICE))
segmentador:      ## regras × modelo do segmentador (rótulo prata dos títulos)
	uv run --group treino python -m treino.segmentador
resultado-pedido: ## regras × modelo do resultado do recurso
	uv run --group treino python -m treino.resultado_pedido
configuracoes:    ## quatro configurações (LLM, +RAG, +reranker, +verificador) com Ollama aberto
	uv run --group worker python -m avaliacao.configuracoes.rodar --modelos $(or $(MODELOS),qwen3:8b)
extrator-campos:  ## acerto do extrator de campos contra os metadados do RepoJus
	uv run --group treino python -m treino.extrator_campos
intencao:         ## intenção da guarda: regras × TF-IDF de caracteres
	uv run --group treino python -m treino.intencao avaliar
registrar-cross-encoders: ## reranker, NLI e embeddings no registro do MLflow (alias candidato)
	uv run --group treino python -m treino.registrar_cross_encoders
ruido-ocr:        ## queda dos componentes em uso com ruído de OCR (sintético) e ajuste com aumento
	uv run --group treino python -m treino.ruido_ocr
deriva:           ## relatório Evidently de deriva sobre o log de previsões do worker
	uv run --group treino python -m treino.deriva relatorio
aprendizado-ativo: ## lote de anotação (Label Studio) com as previsões abaixo do limiar
	uv run --group treino python -m treino.aprendizado_ativo
