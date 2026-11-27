"""Benchmark do verificador NLI nos pares-ouro (issue #17, RF06/RNF04).

    uv run --group worker --group treino python -m treino.benchmark_nli [--modelos A B ...] [--device mps]

Todos os candidatos passam pelo **mesmo julgamento da Validação** (`validacao.melhor_janela`: o trecho é dividido em
janelas e fica a de maior p(sustenta)), sobre os mesmos pares (`avaliacao/pares_ouro/verificador_v1.jsonl`).
Para cada candidato mede:

- F1 por classe (sustenta, contradiz, não trata) do veredito da melhor janela;
- precisão e recall de "sustenta" no limiar em uso (`validacao.LIMIAR_SUSTENTA`) e no limiar escolhido pela regra do
  portão (menor limiar com precisão ≥ 0,90 — a mesma de `avaliacao/agentes/calibrar_nli.py`);
- os mesmos números com a Validação completa (regras de saída antes do NLI) e no subconjunto adversarial;
- latência por par e memória do modelo carregado.

Baseline (regra da decisão 0004): sobreposição lexical frase × trecho como p(sustenta), sem modelo.

Saída: `treino/relatorios/benchmark_nli.{json,md}` e um run por candidato no experimento `benchmark_nli` do MLflow.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from treino.comum import RAIZ, RELATORIOS, salvar_json, sha256_arquivo

PARES = RAIZ / "avaliacao" / "pares_ouro" / "verificador_v1.jsonl"
ROTULOS = ("sustenta", "contradiz", "nao_trata")
PRECISAO_MINIMA = 0.90
BASELINE = "baseline_sobreposicao_lexical"
CANDIDATOS = (
    "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli",
    "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7",
    "MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli",
)


# ---------------------------------------------------------------- funções puras (testadas no CI)
def carregar_pares(caminho: Path = PARES) -> list[dict]:
    return [json.loads(linha) for linha in caminho.read_text(encoding="utf-8").splitlines() if linha.strip()]


def adversarial(par: dict) -> bool:
    return "bateria" not in par.get("origem", "")


def binario(pares: list[dict], limiar: float, chave: str = "p") -> dict:
    """Precisão e recall de 'sustenta' liberando a frase quando p >= limiar."""
    vp = sum(p[chave] >= limiar and p["rotulo"] == "sustenta" for p in pares)
    fp = sum(p[chave] >= limiar and p["rotulo"] != "sustenta" for p in pares)
    fn = sum(p[chave] < limiar and p["rotulo"] == "sustenta" for p in pares)
    precisao = vp / (vp + fp) if vp + fp else 1.0
    recall = vp / (vp + fn) if vp + fn else 0.0
    f1 = 2 * precisao * recall / (precisao + recall) if precisao + recall else 0.0
    return {"limiar": round(limiar, 2), "precisao": round(precisao, 3), "recall": round(recall, 3), "f1": round(f1, 3),
            "liberadas_falsas": fp, "barradas_boas": fn}


def escolher_limiar(pares: list[dict], chave: str = "p") -> tuple[dict, bool]:
    tabela = [binario(pares, x / 100, chave) for x in range(5, 100, 5)]
    ok = [m for m in tabela if m["precisao"] >= PRECISAO_MINIMA and m["recall"] > 0]
    if ok:
        return min(ok, key=lambda m: m["limiar"]), True
    return max(tabela, key=lambda m: (m["precisao"], m["recall"])), False


def f1_tres_classes(pares: list[dict]) -> dict:
    from treino.metricas import f1_por_classe

    por = f1_por_classe([p["rotulo"] for p in pares], [p["veredito"] for p in pares], ROTULOS)
    return {"f1_macro": round(sum(c["f1"] for c in por.values()) / len(ROTULOS), 3),
            "por_classe": {k: {m: round(v, 3) if isinstance(v, float) else v for m, v in c.items()} for k, c in por.items()}}


def resumir(pares: list[dict], limiar_em_uso: float) -> dict:
    """Métricas de um candidato. Cada par precisa de: rotulo, origem, p_nli, veredito, p (com regras)."""
    escolhido_nli, ok_nli = escolher_limiar(pares, "p_nli")
    escolhido, ok = escolher_limiar(pares, "p")
    adv = [p for p in pares if adversarial(p)]
    return {
        "tres_classes": f1_tres_classes(pares),
        "so_nli": {"em_uso": binario(pares, limiar_em_uso, "p_nli"), "escolhido": escolhido_nli, "atingiu_portao": ok_nli},
        "validacao_completa": {"em_uso": binario(pares, limiar_em_uso, "p"), "escolhido": escolhido, "atingiu_portao": ok},
        "adversarial": {"n": len(adv), "em_uso": binario(adv, limiar_em_uso, "p") if adv else None},
        # erro grave do verificador: frase contraditada pelo trecho liberada como sustentada
        "contradicoes_liberadas_em_uso": sum(p["p"] >= limiar_em_uso and p["rotulo"] == "contradiz" for p in pares),
    }


# ---------------------------------------------------------------- execução
def _pontuar_baseline(pares: list[dict]) -> None:
    from worker.evidencia.agentes.validacao import sobreposicao

    for p in pares:
        p["p_nli"] = sobreposicao(p["frase"], p["trecho"])
        p["veredito"] = "sustenta" if p["p_nli"] >= 0.5 else "nao_trata"
        p["janela"] = p["trecho"]


def _pontuar_modelo(pares: list[dict], modelo: str, device: str | None) -> dict:
    from worker.evidencia.agentes.validacao import melhor_janela
    from worker.evidencia.verificador import VerificadorNLI

    t0 = time.perf_counter()
    ver = VerificadorNLI(modelo, device=device)
    carga_s = time.perf_counter() - t0
    params = sum(p.numel() for p in ver.net.parameters())
    tempos = []
    for i, p in enumerate(pares, 1):
        t = time.perf_counter()
        p["veredito"], probs, p["janela"] = melhor_janela(ver, p["frase"], p["trecho"])
        tempos.append(time.perf_counter() - t)
        p["p_nli"] = probs["sustenta"]
        print(f"  {i:3d}/{len(pares)} {p['rotulo']:>10} → {p['veredito']:>10} p={p['p_nli']:.3f}", flush=True)
    tempos.sort()
    return {"carga_s": round(carga_s, 1), "parametros_m": round(params / 1e6, 1),
            "memoria_pesos_mb": round(params * 4 / 2**20),  # fp32
            "latencia_par_ms_mediana": round(1000 * tempos[len(tempos) // 2]),
            "latencia_par_ms_p95": round(1000 * tempos[int(len(tempos) * 0.95) - 1])}


def _aplicar_regras(pares: list[dict]) -> None:
    from worker.evidencia.agentes.validacao import motivo_na_janela, motivo_por_regra

    for p in pares:
        regra = motivo_por_regra(p["frase"], p["trecho"]) or motivo_na_janela(p["frase"], p.get("janela") or p["trecho"])
        p["regra"] = regra
        p["p"] = 0.0 if regra else p["p_nli"]


def rodar(modelos: list[str], device: str | None, pares_caminho: Path, mlflow_ok: bool) -> dict:
    from worker.evidencia.agentes.validacao import LIMIAR_SUSTENTA

    base = carregar_pares(pares_caminho)
    resultados: dict[str, dict] = {}
    for modelo in [BASELINE, *modelos]:
        print(f"→ {modelo}", flush=True)
        pares = [dict(p) for p in base]
        try:
            custo = {} if modelo == BASELINE else _pontuar_modelo(pares, modelo, device)
        except Exception as e:  # modelo não baixado, sem rede, tokenizer incompatível
            print(f"  pulado: {e}", flush=True)
            resultados[modelo] = {"erro": str(e)[:300]}
            continue
        if modelo == BASELINE:
            _pontuar_baseline(pares)
        _aplicar_regras(pares)
        resultados[modelo] = {**resumir(pares, LIMIAR_SUSTENTA), "custo": custo,
                              "probabilidades": [{"id": p["id"], "p_nli": round(p["p_nli"], 4), "veredito": p["veredito"]}
                                                 for p in pares]}
    relatorio = {"pares": str(pares_caminho.relative_to(RAIZ)), "pares_sha256": sha256_arquivo(pares_caminho),
                 "n": len(base), "rotulos": {r: sum(p["rotulo"] == r for p in base) for r in ROTULOS},
                 "limiar_em_uso": LIMIAR_SUSTENTA, "device": device or "cpu", "resultados": resultados}
    if mlflow_ok:
        _registrar_mlflow(relatorio)
    return relatorio


def _registrar_mlflow(rel: dict) -> None:
    from treino.comum import iniciar_mlflow, tags_padrao

    mlflow = iniciar_mlflow("benchmark_nli")
    for modelo, r in rel["resultados"].items():
        if "erro" in r:
            continue
        with mlflow.start_run(run_name=modelo.split("/")[-1]):
            mlflow.set_tags(tags_padrao(tarefa="verificador_nli", modelo=modelo, **{"dados.pares_sha256": rel["pares_sha256"]}))
            mlflow.log_params({"modelo": modelo, "limiar_em_uso": rel["limiar_em_uso"], "device": rel["device"]})
            vc = r["validacao_completa"]
            mlflow.log_metrics({
                "f1_macro_3_classes": r["tres_classes"]["f1_macro"],
                "em_uso.precisao": vc["em_uso"]["precisao"], "em_uso.recall": vc["em_uso"]["recall"],
                "escolhido.limiar": vc["escolhido"]["limiar"], "escolhido.precisao": vc["escolhido"]["precisao"],
                "escolhido.recall": vc["escolhido"]["recall"],
                "so_nli.em_uso.precisao": r["so_nli"]["em_uso"]["precisao"],
                "contradicoes_liberadas_em_uso": r["contradicoes_liberadas_em_uso"],
                **{f"custo.{k}": v for k, v in r["custo"].items()},
            })
            mlflow.log_dict({k: v for k, v in r.items() if k != "probabilidades"}, "metricas.json")


def markdown(rel: dict) -> str:
    lin = [
        "# Benchmark do verificador NLI nos pares-ouro",
        "",
        f"{rel['n']} pares de `{rel['pares']}` (sha256 `{rel['pares_sha256'][:12]}…`; "
        + ", ".join(f"{v} {k}" for k, v in rel["rotulos"].items())
        + f"). Mesmo julgamento da Validação (melhor janela). Limiar em uso: **{rel['limiar_em_uso']}**. "
        f"Device: {rel['device']}. **Rótulos em rascunho**: aguardam o aceite da Curadoria.",
        "",
        "| Candidato | F1 macro (3 classes) | Só NLI no limiar em uso (P / R) | Validação completa no limiar em uso (P / R) "
        "| Limiar do portão (P / R) | Adversarial (P / R) | Contradições liberadas | Latência mediana/par | Parâmetros |",
        "|---|---:|---|---|---|---|---:|---:|---:|",
    ]
    for modelo, r in rel["resultados"].items():
        if "erro" in r:
            lin.append(f"| `{modelo}` | não rodou: {r['erro'][:80]} |||||||")
            continue
        sn, vc, adv, c = r["so_nli"]["em_uso"], r["validacao_completa"], r["adversarial"]["em_uso"], r["custo"]
        esc = vc["escolhido"]
        lin.append(
            f"| `{modelo}` | {r['tres_classes']['f1_macro']} | {sn['precisao']} / {sn['recall']} | "
            f"{vc['em_uso']['precisao']} / {vc['em_uso']['recall']} | "
            f"{esc['limiar']} ({esc['precisao']} / {esc['recall']}){'' if vc['atingiu_portao'] else ' ⚠️'} | "
            f"{adv['precisao']} / {adv['recall']} | {r['contradicoes_liberadas_em_uso']} | "
            f"{c.get('latencia_par_ms_mediana', '—')} ms | {c.get('parametros_m', '—')} M |"
        )
    lin += ["", "⚠️ = nenhum limiar atinge precisão 0,90; mostrado o de maior precisão.", "",
            "Regra de troca (decisão 0004): o candidato só substitui o verificador em uso se tiver precisão ≥ 0,90 na "
            "Validação completa com recall maior, sem liberar mais contradições, e couber no orçamento de memória do "
            "worker (`treino/relatorios/memoria_latencia_m4.md`)."]
    return "\n".join(lin) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--modelos", nargs="*", default=list(CANDIDATOS))
    ap.add_argument("--pares", type=Path, default=PARES)
    ap.add_argument("--device", default=None, help="mps no Mac, cuda numa GPU NVIDIA")
    ap.add_argument("--sem-mlflow", action="store_true")
    ap.add_argument("--saida", default="benchmark_nli", help="nome do relatório em treino/relatorios/")
    a = ap.parse_args()
    rel = rodar(a.modelos, a.device, a.pares, not a.sem_mlflow)
    salvar_json(rel, RELATORIOS / f"{a.saida}.json")
    (RELATORIOS / f"{a.saida}.md").write_text(markdown(rel), encoding="utf-8")
    print(markdown(rel))


if __name__ == "__main__":
    main()
