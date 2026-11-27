"""Baselines do segmentador (issue #17, bloqueio da #15): regras × modelo, acerto por parte da decisão.

    uv run --group treino python -m treino.segmentador [--docs 3000] [--sem-mlflow]

**Rótulo fraco (prata).** Os acórdãos do RepoJus (mesmo lote do classificador de tipo) trazem os títulos das seções
em linha própria em quase todos os documentos (EMENTA 100%, RELATÓRIO 93%, FUNDAMENTAÇÃO/VOTO 96%, CONCLUSÃO 99%,
ACORDAM 99,7%). A máquina de estados de `worker.leitura.segmentador.parte_por_marcador` sobre esses títulos dá a parte
de cada parágrafo. Documento sem RELATÓRIO, sem FUNDAMENTAÇÃO/VOTO ou sem dispositivo fica fora (rótulo não confiável).

**Tarefa avaliada.** Com os títulos o rótulo é a própria regra (circular), então a avaliação é **sem os títulos**: as
linhas de marcador são removidas, como acontece num trecho colado, numa foto cortada ou numa sentença fora do padrão.
Compara:
  1. classe majoritária;
  2. regra de posição (cortes na posição relativa do parágrafo, ajustados no treino);
  3. TF-IDF + regressão logística no texto do parágrafo + faixa de posição.

Divisão por processo (`classificador_tipo.divisao`). Saída: `treino/relatorios/segmentador.{json,md}`.
"""

from __future__ import annotations

import argparse
from collections import Counter

from treino.comum import RELATORIOS, parametros, salvar_json

PARTES = ("outro", "relatorio", "fundamentacao", "dispositivo")
FAIXAS = 10


# ---------------------------------------------------------------- funções puras (testadas no CI)
def paragrafos(texto: str) -> list[str]:
    """Quebra o texto em parágrafos: linha em branco ou linha de marcador começam um novo."""
    from worker.leitura.segmentador import parte_por_marcador

    out: list[list[str]] = []
    atual: list[str] = []
    for linha in texto.split("\n"):
        s = linha.strip()
        if not s:
            if atual:
                out.append(atual)
                atual = []
            continue
        if parte_por_marcador(s, "fundamentacao") and atual:
            out.append(atual)
            atual = []
        atual.append(s)
    if atual:
        out.append(atual)
    return ["\n".join(p) for p in out]


def rotular_fraco(pars: list[str]) -> list[tuple[str, str, bool]] | None:
    """[(parágrafo, parte, é_marcador)] pela máquina de estados; None se faltar alguma seção principal."""
    from worker.leitura.segmentador import parte_por_marcador

    parte = "outro"
    out = []
    for p in pars:
        nova = parte_por_marcador(p, parte)
        parte = nova or parte
        out.append((p, parte, nova is not None))
    vistas = {pt for _, pt, _ in out}
    return out if {"relatorio", "fundamentacao", "dispositivo"} <= vistas else None


def sem_marcador(p: str) -> str:
    """Tira a linha de título do parágrafo (o resto do parágrafo fica)."""
    linhas = p.split("\n")
    return "\n".join(linhas[1:]).strip()


def faixa(i: int, n: int) -> int:
    return min(FAIXAS - 1, int(FAIXAS * i / max(n, 1)))


def ajustar_cortes(exemplos: list[tuple[float, str]]) -> tuple[float, float, float]:
    """Cortes c1 < c2 < c3 na posição relativa (outro | relatório | fundamentação | dispositivo) que maximizam o acerto."""
    grade = [x / 100 for x in range(0, 101, 5)]
    melhor, cortes = -1, (0.05, 0.15, 0.9)
    for c1 in grade:
        for c2 in (g for g in grade if g >= c1):
            for c3 in (g for g in grade if g >= c2):
                acerto = sum(prever_posicao(pos, (c1, c2, c3)) == y for pos, y in exemplos)
                if acerto > melhor:
                    melhor, cortes = acerto, (c1, c2, c3)
    return cortes


def prever_posicao(pos: float, cortes: tuple[float, float, float]) -> str:
    c1, c2, c3 = cortes
    return "outro" if pos < c1 else "relatorio" if pos < c2 else "fundamentacao" if pos < c3 else "dispositivo"


# ---------------------------------------------------------------- execução
def montar_exemplos(df) -> list[dict]:
    ex = []
    for processo, div, texto in zip(df.processo, df.divisao, df.texto, strict=True):
        rot = rotular_fraco(paragrafos(texto))
        if rot is None:
            continue
        corpo = [(sem_marcador(p) if m else p, y) for p, y, m in rot]
        corpo = [(p, y) for p, y in corpo if p]
        n = len(corpo)
        for i, (p, y) in enumerate(corpo):
            ex.append({"processo": processo, "divisao": div, "texto": p[:2000], "parte": y, "pos": i / max(n - 1, 1),
                       "faixa": faixa(i, n)})
    return ex


def avaliar(y_true: list[str], y_pred: list[str]) -> dict:
    from treino.metricas import f1_por_classe

    por = f1_por_classe(y_true, y_pred, PARTES)
    return {"acuracia": sum(a == b for a, b in zip(y_true, y_pred, strict=True)) / len(y_true),
            "f1_macro": sum(c["f1"] for c in por.values()) / len(PARTES),
            "acerto_por_parte": {p: por[p]["recall"] for p in PARTES}, "por_classe": por,
            # erro grave: trecho do dispositivo lido como fundamentação ou vice-versa (muda o "resultado")
            "dispositivo_trocado": sum((a == "dispositivo") != (b == "dispositivo")
                                       for a, b in zip(y_true, y_pred, strict=True))}


def rodar(a) -> dict:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression

    from treino.classificador_tipo import carregar_lote

    df = carregar_lote()
    if a.docs:
        df = df.sample(n=min(a.docs, len(df)), random_state=7)
    ex = montar_exemplos(df)
    docs_ok = len({e["processo"] for e in ex})
    por_div = {d: [e for e in ex if e["divisao"] == d] for d in ("treino", "validacao", "teste")}
    print({d: len(v) for d, v in por_div.items()}, f"docs com rótulo: {docs_ok}/{len(df)}", flush=True)
    res: dict[str, dict] = {}

    maj = Counter(e["parte"] for e in por_div["treino"]).most_common(1)[0][0]
    res["majoritaria"] = {d: avaliar([e["parte"] for e in v], [maj] * len(v)) for d, v in por_div.items() if d != "treino"}

    amostra_cortes = [(e["pos"], e["parte"]) for e in por_div["treino"][:: max(1, len(por_div["treino"]) // 3000)]]
    cortes = ajustar_cortes(amostra_cortes)
    res["regra_posicao"] = {d: avaliar([e["parte"] for e in v], [prever_posicao(e["pos"], cortes) for e in v])
                            for d, v in por_div.items() if d != "treino"}
    res["regra_posicao"]["cortes"] = cortes

    def entrada(e):
        return f"FAIXA{e['faixa']} " * 3 + e["texto"]

    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=3, max_features=200_000, sublinear_tf=True, strip_accents="unicode")
    xtr = vec.fit_transform([entrada(e) for e in por_div["treino"]])
    lr = LogisticRegression(C=4.0, max_iter=2000, class_weight="balanced")
    lr.fit(xtr, [e["parte"] for e in por_div["treino"]])
    res["tfidf_lr_texto_posicao"] = {
        d: avaliar([e["parte"] for e in v], list(lr.predict(vec.transform([entrada(e) for e in v]))))
        for d, v in por_div.items() if d != "treino"}

    rel = {"docs_amostrados": len(df), "docs_com_rotulo": docs_ok,
           "paragrafos": {d: len(v) for d, v in por_div.items()},
           "distribuicao_treino": dict(Counter(e["parte"] for e in por_div["treino"])), "resultados": res}
    if not a.sem_mlflow:
        from treino.comum import iniciar_mlflow, tags_padrao

        mlflow = iniciar_mlflow("segmentador")
        for nome, r in res.items():
            with mlflow.start_run(run_name=nome):
                mlflow.set_tags(tags_padrao(tarefa="segmentador", variante=nome, rotulo="prata — títulos das seções"))
                mlflow.log_params({"docs": len(df), "variante": nome})
                for d in ("validacao", "teste"):
                    mlflow.log_metrics({f"{d}.f1_macro": r[d]["f1_macro"], f"{d}.acuracia": r[d]["acuracia"],
                                        f"{d}.dispositivo_trocado": r[d]["dispositivo_trocado"]})
    return rel


def markdown(rel: dict) -> str:
    lin = ["# Segmentador: regras × modelo (acórdãos sem os títulos das seções)", "",
           f"{rel['docs_com_rotulo']} de {rel['docs_amostrados']} acórdãos com rótulo fraco confiável; parágrafos "
           + ", ".join(f"{d} {n}" for d, n in rel["paragrafos"].items()) + ". **Rótulo prata** (títulos das seções); "
           "a Curadoria e a Cientista de dados validam uma amostra antes de virar ouro.", "",
           "| Variante | F1 macro | Acurácia | " + " | ".join(f"Acerto {p}" for p in PARTES) + " | Dispositivo trocado |",
           "|---|---:|---:|" + "---:|" * len(PARTES) + "---:|"]
    for nome, r in rel["resultados"].items():
        t = r["teste"]
        lin.append(f"| {nome} | {t['f1_macro']:.3f} | {t['acuracia']:.3f} | "
                   + " | ".join(f"{t['acerto_por_parte'][p]:.3f}" for p in PARTES) + f" | {t['dispositivo_trocado']} |")
    cortes = rel["resultados"]["regra_posicao"]["cortes"]
    lin += ["", f"Cortes da regra de posição (ajustados no treino): {cortes}.", "",
            "Com os títulos presentes, a regra de marcadores (`worker/leitura/segmentador.py`) reproduz o rótulo por "
            "construção; ela continua em uso para documento com títulos, e o modelo é o candidato para documento sem."]
    return "\n".join(lin) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--docs", type=int, default=parametros("segmentador").get("docs", 3000),
                    help="acórdãos amostrados (0 = todos)")
    ap.add_argument("--sem-mlflow", action="store_true")
    a = ap.parse_args()
    rel = rodar(a)
    salvar_json(rel, RELATORIOS / "segmentador.json")
    (RELATORIOS / "segmentador.md").write_text(markdown(rel), encoding="utf-8")
    print(markdown(rel))


if __name__ == "__main__":
    main()

