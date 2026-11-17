COMPOSE = docker compose -f infra/docker-compose.yml --env-file .env

.PHONY: setup up down migrar backend worker frontend test lint preparar-modelos

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
