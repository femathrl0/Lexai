"""Portão de regressão de modelo (issue #17; manual, "Portões": candidato pior que o em uso em alguma métrica principal).

    uv run python -m treino.portao_regressao [--linha-base treino/portoes/linha_base.json] [--relatorio m=caminho ...]

Para cada modelo de `treino/portoes/linha_base.json`, lê o relatório gravado pelo script de treino ou benchmark e
compara com a referência:

- **métrica principal** com direção (maior/menor é melhor) e tolerância: reprova se piorar além da tolerância;
- **erro grave** (troca de fase, provido ↔ desprovido, contradição liberada…): reprova se aumentar, sem tolerância.

Roda no CI sem modelos: só lê JSON. Um PR que regrava um relatório com números piores fica vermelho; para mudar a
referência é preciso promover (`treino/promover.py`) ou alterar `linha_base.json` num PR revisado.
Sai com código 1 se algum modelo reprovar.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from treino.comum import RAIZ

LINHA_BASE = RAIZ / "treino" / "portoes" / "linha_base.json"


def extrair(relatorio: dict, caminho: str) -> dict:
    """Desce no JSON por chaves separadas por ponto (as chaves podem ter ':' e '/')."""
    no = relatorio
    for parte in caminho.split("."):
        if not isinstance(no, dict) or parte not in no:
            raise KeyError(f"'{parte}' não existe em '{caminho}'")
        no = no[parte]
    return no


def comparar(nome: str, ref: dict, atual: dict) -> list[str]:
    """Lista de motivos de reprovação (vazia = passou)."""
    falhas = []
    for metrica, regra in ref.get("metricas", {}).items():
        if metrica not in atual or atual[metrica] is None:
            falhas.append(f"{nome}: métrica '{metrica}' ausente no relatório")
            continue
        v, base, tol = float(atual[metrica]), float(regra["valor"]), float(regra.get("tolerancia", 0.0))
        pior = v < base - tol if regra.get("direcao", "maior") == "maior" else v > base + tol
        if pior:
            falhas.append(f"{nome}: {metrica} {v:.4f} pior que a referência {base:.4f} (tolerância {tol})")
    for erro, limite in ref.get("erros_graves", {}).items():
        if erro not in atual:
            falhas.append(f"{nome}: erro grave '{erro}' ausente no relatório")
        elif int(atual[erro]) > int(limite):
            falhas.append(f"{nome}: erro grave {erro} aumentou ({limite} → {atual[erro]})")
    return falhas


def verificar(linha_base: dict, relatorios: dict[str, Path] | None = None, raiz: Path = RAIZ) -> tuple[list[str], list[str]]:
    """(falhas, linhas do resumo)."""
    falhas, resumo = [], []
    for nome, ref in linha_base["modelos"].items():
        caminho = (relatorios or {}).get(nome) or raiz / ref["relatorio"]
        if not Path(caminho).exists():
            falhas.append(f"{nome}: relatório {caminho} não existe")
            continue
        try:
            atual = extrair(json.loads(Path(caminho).read_text(encoding="utf-8")), ref["caminho"])
        except KeyError as e:
            falhas.append(f"{nome}: {e}")
            continue
        f = comparar(nome, ref, atual)
        falhas += f
        valores = ", ".join(f"{m}={atual.get(m)!s:.6}" for m in [*ref.get("metricas", {}), *ref.get("erros_graves", {})])
        resumo.append(f"{'REPROVADO' if f else 'ok':>9}  {nome} ({ref.get('versao_referencia', '')}): {valores}")
    return falhas, resumo


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--linha-base", type=Path, default=LINHA_BASE)
    ap.add_argument("--relatorio", action="append", default=[], metavar="MODELO=CAMINHO",
                    help="avalia um relatório candidato fora do lugar padrão")
    a = ap.parse_args()
    relatorios = {k: Path(v) for k, v in (r.split("=", 1) for r in a.relatorio)}
    falhas, resumo = verificar(json.loads(a.linha_base.read_text(encoding="utf-8")), relatorios)
    print("Portão de regressão de modelo\n" + "\n".join(resumo))
    if falhas:
        print("\nReprovado:\n- " + "\n- ".join(falhas), file=sys.stderr)
        sys.exit(1)
    print("\nAprovado: nenhum modelo piorou em métrica principal nem em erro grave.")


if __name__ == "__main__":
    main()
