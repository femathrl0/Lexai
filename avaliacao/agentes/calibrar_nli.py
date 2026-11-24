"""Calibra o limiar do verificador NLI do Agente de Validação nos pares-ouro.

    uv run --group worker python -m avaliacao.agentes.calibrar_nli [--pares avaliacao/pares_ouro/verificador_v1.jsonl]

Para cada par (frase, trecho, rótulo) roda o mesmo julgamento da Validação: `VerificadorNLI` em cada janela do
trecho (`validacao._janelas`) e fica com a maior p(sustenta). Depois varre o limiar e mede, tratando "sustenta" como
positivo:

- precisão: das frases liberadas, quantas o trecho sustenta de fato (frase falsa liberada = erro grave);
- recall: das frases sustentadas, quantas são liberadas (frase boa barrada = resposta mais pobre).

O limiar é medido sobre a Validação completa: antes do NLI rodam as regras de saída (`validacao.motivo_por_regra`:
conselho, promessa e números/prazos que não estão no trecho); par reprovado por regra conta como p(sustenta)=0.
O relatório também mostra o NLI sozinho, para ver o que cada parte acrescenta.

Regra de escolha (manual: "o verificador é o último portão"): o **menor limiar com precisão ≥ 0,90**, que é o de
maior recall entre os que respeitam o portão. Se nenhum limiar chega lá, usa o de maior precisão e avisa.
Saída: avaliacao/agentes/resultados/<data>_calibracao_nli.{json,md}
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from worker.evidencia.agentes.validacao import melhor_janela, motivo_na_janela, motivo_por_regra

AQUI = Path(__file__).resolve().parent
PARES = AQUI.parent / "pares_ouro" / "verificador_v1.jsonl"
PRECISAO_MINIMA = 0.90


def p_sustenta(verificador, frase: str, trecho: str) -> tuple[float, str, str]:
    veredito, probs, janela = melhor_janela(verificador, frase, trecho)
    return probs["sustenta"], veredito, janela


def metricas(pares: list[dict], limiar: float) -> dict:
    vp = sum(p["p"] >= limiar and p["rotulo"] == "sustenta" for p in pares)
    fp = sum(p["p"] >= limiar and p["rotulo"] != "sustenta" for p in pares)
    fn = sum(p["p"] < limiar and p["rotulo"] == "sustenta" for p in pares)
    precisao = vp / (vp + fp) if vp + fp else 1.0
    recall = vp / (vp + fn) if vp + fn else 0.0
    f1 = 2 * precisao * recall / (precisao + recall) if precisao + recall else 0.0
    return dict(limiar=round(limiar, 2), precisao=round(precisao, 3), recall=round(recall, 3), f1=round(f1, 3),
                liberadas_falsas=fp, barradas_boas=fn)


def escolher(tabela: list[dict]) -> tuple[dict, bool]:
    ok = [m for m in tabela if m["precisao"] >= PRECISAO_MINIMA and m["recall"] > 0]
    if ok:
        return min(ok, key=lambda m: m["limiar"]), True
    return max(tabela, key=lambda m: (m["precisao"], m["recall"])), False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pares", type=Path, default=PARES)
    ap.add_argument("--modelo", help="cross-encoder NLI (padrão: o do verificador)")
    ap.add_argument("--reusar", type=Path, help="JSON de uma calibração anterior: reaproveita p(sustenta) do NLI")
    ap.add_argument("--limiar-lexical", type=float, default=None,
                    help="sobreposição mínima frase × trecho (regra de saída); padrão: validacao.LIMIAR_LEXICAL")
    ap.add_argument("--device", default=None, help="mps no Mac (o NLI na CPU é ~7× mais lento)")
    ap.add_argument("--sufixo", default="", help="sufixo do arquivo de saída, para comparar configurações")
    ap.add_argument("--sem-regra-janela", action="store_true", help="não confere números contra a janela do NLI")
    a = ap.parse_args()

    from worker.evidencia.verificador import MODELO_PADRAO

    pares = [json.loads(linha) for linha in a.pares.read_text(encoding="utf-8").splitlines() if linha.strip()]
    if a.reusar:
        anterior = json.loads(a.reusar.read_text(encoding="utf-8"))
        nli = {x["id"]: x.get("p_nli", x.get("p")) for x in anterior["probabilidades"]}
        janelas = {x["id"]: x.get("janela") for x in anterior["probabilidades"]}
        modelo = anterior["modelo"]
        for p in pares:
            p["p_nli"], p["janela"] = nli[p["id"]], janelas[p["id"]]
    else:
        from worker.evidencia.verificador import VerificadorNLI

        ver = VerificadorNLI(a.modelo or MODELO_PADRAO, device=a.device)
        modelo = ver.modelo
        for i, p in enumerate(pares, 1):
            p["p_nli"], _, p["janela"] = p_sustenta(ver, p["frase"], p["trecho"])
            print(f"{i:3d}/{len(pares)} {p['rotulo']:>10} p={p['p_nli']:.3f}", flush=True)
    for p in pares:
        p["regra"] = motivo_por_regra(p["frase"], p["trecho"], a.limiar_lexical)
        if not p["regra"] and not a.sem_regra_janela and p.get("janela"):
            p["regra"] = motivo_na_janela(p["frase"], p["janela"])
        p["p"] = 0.0 if p["regra"] else p["p_nli"]

    so_nli = [dict(p, p=p["p_nli"]) for p in pares]
    tabela = [metricas(pares, x / 100) for x in range(5, 100, 5)]
    escolhido, atingiu = escolher(tabela)
    atual = metricas(pares, 0.5)
    por_origem = {}
    for origem in sorted({p["origem"] for p in pares}):
        sub = [p for p in pares if p["origem"] == origem]
        por_origem[origem] = dict(n=len(sub), no_escolhido=metricas(sub, escolhido["limiar"]), em_0_5=metricas(sub, 0.5))
    erros = [dict(id=p["id"], rotulo=p["rotulo"], p=round(p["p"], 3), frase=p["frase"], fonte=p["fonte"])
             for p in pares if (p["p"] >= escolhido["limiar"]) != (p["rotulo"] == "sustenta")]

    saida = AQUI / "resultados" / f"{date.today():%Y-%m-%d}_calibracao_nli{a.sufixo}"
    nli_no_escolhido = metricas(so_nli, escolhido["limiar"])
    barradas_por_regra = [dict(id=p["id"], rotulo=p["rotulo"], motivo=p["regra"]) for p in pares if p["regra"]]
    resultado = dict(modelo=modelo, pares=str(a.pares.relative_to(AQUI.parents[1])), n=len(pares),
                     rotulos={r: sum(p["rotulo"] == r for p in pares) for r in ("sustenta", "contradiz", "nao_trata")},
                     regra=f"menor limiar com precisão ≥ {PRECISAO_MINIMA}", atingiu_portao=atingiu,
                     escolhido=escolhido, limiar_anterior_0_5=atual, so_nli_no_escolhido=nli_no_escolhido,
                     so_nli_em_0_5=metricas(so_nli, 0.5), barradas_por_regra=barradas_por_regra,
                     tabela=tabela, por_origem=por_origem,
                     erros_no_escolhido=erros, probabilidades=[dict(id=p["id"], rotulo=p["rotulo"], p_nli=round(p["p_nli"], 4),
                                                                    p=round(p["p"], 4), janela=p.get("janela"))
                                                               for p in pares])
    (saida.parent / (saida.name + ".json")).write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    linhas = [f"# Calibração do limiar do NLI — {date.today():%d/%m/%Y}\n",
              f"Modelo `{modelo}` · {len(pares)} pares de `{resultado['pares']}` "
              f"({', '.join(f'{v} {k}' for k, v in resultado['rotulos'].items())}) · regra: {resultado['regra']}\n",
              f"**Limiar escolhido: {escolhido['limiar']}** — precisão {escolhido['precisao']}, recall "
              f"{escolhido['recall']} (antes, em 0,5: precisão {atual['precisao']}, recall {atual['recall']})"
              + ("" if atingiu else " — **nenhum limiar atingiu o portão; usado o de maior precisão**") + "\n",
              "| limiar | precisão | recall | F1 | falsas liberadas | boas barradas |", "|---|---|---|---|---|---|"]
    linhas += [f"| {m['limiar']} | {m['precisao']} | {m['recall']} | {m['f1']} | {m['liberadas_falsas']} | "
               f"{m['barradas_boas']} |" for m in tabela]
    so = resultado["so_nli_em_0_5"]
    linhas += [f"\nSó o NLI, sem as regras: em 0,5 precisão {so['precisao']} / recall {so['recall']}; no limiar escolhido "
               f"precisão {nli_no_escolhido['precisao']} / recall {nli_no_escolhido['recall']}.\n",
               "## Pares barrados pelas regras antes do NLI\n", "| id | rótulo | motivo |", "|---|---|---|"]
    linhas += [f"| {b['id']} | {b['rotulo']} | {b['motivo']} |" for b in barradas_por_regra]
    linhas += ["\n## Por origem dos pares\n", "| origem | n | precisão / recall no escolhido | em 0,5 |", "|---|---|---|---|"]
    linhas += [f"| {o} | {v['n']} | {v['no_escolhido']['precisao']} / {v['no_escolhido']['recall']} | "
               f"{v['em_0_5']['precisao']} / {v['em_0_5']['recall']} |" for o, v in por_origem.items()]
    linhas += ["\n## Erros no limiar escolhido\n", "| id | rótulo | p(sustenta) | frase | fonte |", "|---|---|---|---|---|"]
    linhas += [f"| {e['id']} | {e['rotulo']} | {e['p']} | {e['frase']} | {e['fonte']} |" for e in erros]
    (saida.parent / (saida.name + ".md")).write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print("\n".join(linhas[:3]), f"\n→ {saida}.md")


if __name__ == "__main__":
    main()
