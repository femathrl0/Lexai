"""Utilidades compartilhadas pelos scripts de treino e benchmark (Eng. de ML e MLOps).

Todo experimento registra no MLflow: commit do código, hash dos dados e máquina. Sem isso o resultado não
entra em decisão nenhuma (manual, "Rastrear todo experimento").
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
RELATORIOS = RAIZ / "treino" / "relatorios"
TRACKING_PADRAO = "http://127.0.0.1:15000"


def sha256_arquivo(caminho: str | Path, bloco: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        while chunk := f.read(bloco):
            h.update(chunk)
    return h.hexdigest()


def commit_atual() -> str:
    try:
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=RAIZ, text=True).strip()
        sujo = subprocess.run(["git", "diff", "--quiet"], cwd=RAIZ).returncode != 0
        return sha + ("-sujo" if sujo else "")
    except (OSError, subprocess.CalledProcessError):
        return "desconhecido"


def maquina() -> dict[str, str]:
    info = {"so": platform.platform(), "python": platform.python_version(), "cpu": platform.processor()}
    try:
        info["chip"] = subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip()
        info["ram_gb"] = str(round(int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)) / 2**30))
    except (OSError, subprocess.CalledProcessError):
        pass
    return info


def iniciar_mlflow(experimento: str):
    """Configura o MLflow do Compose (ou MLFLOW_TRACKING_URI) e devolve o módulo pronto para uso."""
    import mlflow

    mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", TRACKING_PADRAO))
    mlflow.set_experiment(experimento)
    return mlflow


def tags_padrao(**extra: str) -> dict[str, str]:
    tags = {"git_commit": commit_atual(), "cargo": "eng-ml", **{f"maquina.{k}": v for k, v in maquina().items()}}
    tags.update(extra)
    return tags


def salvar_json(obj, caminho: str | Path) -> Path:
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return caminho
