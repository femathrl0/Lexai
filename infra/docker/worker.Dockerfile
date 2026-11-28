# Worker: o único processo que carrega modelos. Torch CPU por padrão (índice CPU do PyTorch no uv.lock); para GPU
# NVIDIA, use um host com o Ollama/LLM na GPU e mantenha os encoders na CPU, ou gere uma imagem com TORCH_INDEX=cu124.
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.4 /uv /bin/uv
ARG COM_OCR=false
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 HF_HOME=/modelos/hf
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-default-groups --group worker $( [ "$COM_OCR" = true ] && echo --group ocr ) --no-install-project
COPY contratos contratos
COPY comum comum
COPY worker worker
COPY prompts prompts
COPY corpus corpus
COPY dados/processed dados/processed
COPY scripts/preparar_modelos.sh scripts/
RUN useradd --uid 10001 --create-home lexai && mkdir -p /modelos/hf /app/dados/output && chown -R lexai /modelos /app/dados/output
USER lexai
# Pesos do Hugging Face num volume (/modelos): baixados uma vez com `docker compose run worker python -m worker.baixar_modelos`
VOLUME ["/modelos"]
HEALTHCHECK --interval=30s --timeout=5s --retries=5 CMD python -m worker.saude
CMD ["python", "-m", "worker.main"]
