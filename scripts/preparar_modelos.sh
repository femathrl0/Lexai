#!/usr/bin/env bash
# Primeiro dia, passo 3: baixa a LLM quantizada, o modelo de embeddings e os cross-encoders candidatos.
# Os modelos são candidatos; a escolha final é por benchmark (semanas 2 e 3).
set -euo pipefail
LLM="${LLM_MODELO:-qwen3:8b-q8_0}"
command -v ollama >/dev/null || { echo "Instale o Ollama: https://ollama.com"; exit 1; }
ollama pull "$LLM"
uv run --group worker python - <<'PY'
from huggingface_hub import snapshot_download
for repo in ["BAAI/bge-m3", "BAAI/bge-reranker-v2-m3", "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7"]:
    print("baixando", repo); snapshot_download(repo)
PY
echo "Memória livre:"; vm_stat | awk '/Pages free/ {printf "%.1f GB\n", $3*16384/1e9}'
