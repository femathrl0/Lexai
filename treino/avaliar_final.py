"""Métricas finais nos conjuntos de teste congelados (issue #45).

    uv run --group treino python -m treino.avaliar_final [--rodar]

1. Confere que os conjuntos de teste não mudaram (`treino/teste_congelado.py`; a divisão por hash do processo do
   RepoJus é congelada pela semente).
2. Com `--rodar`, refaz as avaliações baratas (segmentador, resultado, extrator, intenção, ruído de OCR) com o código
   atual; sem ela, só consolida os relatórios gravados.
3. Junta, por modelo em uso, a métrica principal, o erro grave e a versão (de `worker/modelos/em_uso.yml`) e passa
   pelo portão de regressão.

Saída: `treino/relatorios/final.{json,md}`.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys

from treino.comum import RAIZ, RELATORIOS, commit_atual, salvar_json

RAPIDOS = ["treino.segmentador --sem-mlflow", "treino.resultado_pedido --sem-mlflow", "treino.extrator_campos",
           "treino.intencao avaliar --sem-mlflow", "treino.ruido_ocr"]


def consolidar() -> dict:
    from treino.portao_regressao import LINHA_BASE, extrair, verificar
    from worker.modelos.registro import carregar_em_uso

    base = json.loads(LINHA_BASE.read_text(encoding="utf-8"))
    em_uso = carregar_em_uso(tracking_uri="")
    linhas = []
    for nome, ref in base["modelos"].items():
        atual = extrair(json.loads((RAIZ / ref["relatorio"]).read_text(encoding="utf-8")), ref["caminho"])
        modelo = em_uso.get(nome.split(".")[0]) if ref.get("em_uso", True) else None
        linhas.append({"modelo": nome, "em_uso": ref.get("em_uso", True),
                       "versao": modelo.rotulo if modelo else ref.get("versao_referencia"),
                       "referencia": ref.get("versao_referencia"), "relatorio": ref["relatorio"],
                       "metricas": {m: atual.get(m) for m in ref.get("metricas", {})},
                       "erros_graves": {e: atual.get(e) for e in ref.get("erros_graves", {})}})
    falhas, _ = verificar(base)
    return {"commit": commit_atual(), "modelos": linhas, "portao_regressao": "aprovado" if not falhas else falhas}


def markdown(r: dict) -> str:
    lin = ["# Métricas finais — conjuntos de teste congelados", "",
           f"Commit `{r['commit'][:12]}` · conjunto de teste de legislação: **{r['teste_congelado']}** · portão de "
           f"regressão: **{r['portao_regressao'] if isinstance(r['portao_regressao'], str) else 'reprovado'}**.", "",
           "| Modelo | Estágio | Versão | Métrica principal | Erro grave | Relatório |", "|---|---|---|---|---|---|"]
    for x in r["modelos"]:
        met = ", ".join(f"{k} {v:.3f}" for k, v in x["metricas"].items() if v is not None)
        graves = ", ".join(f"{k} {v}" for k, v in x["erros_graves"].items()) or "—"
        estagio = "em uso" if x["em_uso"] else "candidato"
        arq = x["relatorio"].split("/")[-1].replace(".json", ".md")
        lin.append(f"| {x['modelo']} | {estagio} | `{x['versao']}` | {met} | {graves} | [{arq}]({arq}) |")
    lin += ["", "Rótulos: prata (metadados e fórmulas do tribunal) ou rascunho, até o rótulo-ouro da Cientista de dados e o "
            "aceite da Curadoria. O verificador NLI está no relatório de calibração (pares-ouro v1)."]
    return "\n".join(lin) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rodar", action="store_true", help="refaz as avaliações baratas antes de consolidar")
    a = ap.parse_args()
    congelado = subprocess.run([sys.executable, "-m", "treino.teste_congelado"], cwd=RAIZ, capture_output=True, text=True)
    if a.rodar:
        for cmd in RAPIDOS:
            print(f"→ {cmd}", flush=True)
            subprocess.run([sys.executable, "-m", *cmd.split()], cwd=RAIZ, check=True)
    r = consolidar()
    r["teste_congelado"] = "inalterado" if congelado.returncode == 0 else "ALTERADO"
    salvar_json(r, RELATORIOS / "final.json")
    (RELATORIOS / "final.md").write_text(markdown(r), encoding="utf-8")
    print(markdown(r))
    if congelado.returncode or not isinstance(r["portao_regressao"], str):
        sys.exit(1)


if __name__ == "__main__":
    main()
