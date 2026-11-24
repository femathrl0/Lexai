COMPOSE = docker compose -f infra/docker-compose.yml --env-file .env

.PHONY: setup up down migrar backend worker frontend test lint preparar-modelos \
	teste-congelado medir-memoria baseline-tipo benchmark-rerankers

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
