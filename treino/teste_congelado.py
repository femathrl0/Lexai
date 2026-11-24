"""Verifica que o conjunto de teste congelado não mudou (manual: "o teste é fechado na semana 2 e só é usado
para medir, nunca para ajustar").

Reproduz o hash do notebook avaliacao/notebooks/01_legislacao/05_construcao_base_avaliacao.ipynb sobre as
perguntas de teste aprovadas e suas referências, e compara com avaliacao/dados/legislacao/teste_congelado.json.

Uso: python -m treino.teste_congelado
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DIR_LEG = RAIZ / "avaliacao" / "dados" / "legislacao"
CAMPOS_FORA_DO_HASH = ("resultado_referencia", "candidatos")


def hash_teste_legislacao(diretorio: Path = DIR_LEG) -> str:
    perguntas = json.loads((diretorio / "eval_dataset_test_aprovado.json").read_text(encoding="utf-8"))
    referencias = json.loads((diretorio / "referencias_aprovadas.json").read_text(encoding="utf-8"))
    ids = {p["query_id"] for p in perguntas}
    payload = {
        "perguntas": sorted(
            ({k: v for k, v in p.items() if k not in CAMPOS_FORA_DO_HASH} for p in perguntas),
            key=lambda p: p["query_id"],
        ),
        "referencias": sorted((r for r in referencias if r["query_id"] in ids), key=lambda r: r["referencia_id"]),
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def verificar(diretorio: Path = DIR_LEG) -> tuple[bool, str, str]:
    congelado = json.loads((diretorio / "teste_congelado.json").read_text(encoding="utf-8"))["sha256"]
    atual = hash_teste_legislacao(diretorio)
    return atual == congelado, atual, congelado


if __name__ == "__main__":
    ok, atual, congelado = verificar()
    print(f"teste congelado (legislação): {'OK' if ok else 'ALTERADO'}\n  atual     {atual}\n  congelado {congelado}")
    sys.exit(0 if ok else 1)
