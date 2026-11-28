#!/usr/bin/env bash
# Primeiro dia, passo 3: baixa a LLM quantizada, o modelo de embeddings e os cross-encoders.
# Baixa os modelos EM USO (os mesmos de worker/modelos/registro.py) e, com --candidatos, os do benchmark.
set -euo pipefail
LLM="${LLM_MODELO:-qwen3:8b}"   # qwen3:8b-q8_0 não cabe no orçamento de 16 GB (treino/relatorios/memoria_latencia_m4.md)
if command -v ollama >/dev/null; then ollama pull "$LLM"; else echo "Ollama ausente: pulei a LLM (https://ollama.com)"; fi
CANDIDATOS="${1:-}"
uv run --group worker python - "$CANDIDATOS" <<'PY'
import sys
from huggingface_hub import snapshot_download
from worker.modelos.registro import FIXADOS

repos = [m["repo"] for m in FIXADOS.values() if m.get("repo")]
if sys.argv[1] == "--candidatos":
    repos += ["MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7", "MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli",
              "neuralmind/bert-base-portuguese-cased"]
for repo in repos:
    print("baixando", repo); snapshot_download(repo)
PY
echo "Memória livre:"
if command -v vm_stat >/dev/null; then vm_stat | awk '/Pages free/ {printf "%.1f GB\n", $3*16384/1e9}'; else free -g | awk '/Mem:/ {print $7 " GB disponíveis"}'; fi
