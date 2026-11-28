# Backend (FastAPI): só o grupo "backend" — nenhuma biblioteca de ML (tests/backend/test_sem_ml.py).
FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.13.4 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-default-groups --group backend --no-install-project
COPY contratos contratos
COPY comum comum
COPY backend backend
COPY worker/__init__.py worker/filas.py worker/
COPY alembic.ini alembic.ini
COPY infra/migracoes infra/migracoes
RUN useradd --uid 10001 --create-home lexai
USER lexai
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --retries=5 CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/health')"
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
