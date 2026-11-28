"""Baselines do resultado (issue #17, RF03/RNF04): o erro que importa é a troca entre ganhar e perder.

    uv run --group treino python -m treino.resultado_pedido [--sem-mlflow]

**O que dá para medir hoje.** Não há rótulo-ouro por pedido (a Cientista de dados ainda não anotou sentenças). O lote
de acórdãos do TRT-10 permite um rótulo fraco **por recurso**: o parágrafo do ACORDAM diz, com fórmula fixa, se o
recurso foi provido, parcialmente provido, desprovido ou não conhecido. Acórdão com mais de um recurso e resultados
diferentes ("negar provimento ao apelo patronal e dar parcial provimento ao obreiro") fica de fora nesta versão.

**Tarefa.** Ler a CONCLUSÃO do voto (texto diferente do ACORDAM, escrito pelo relator em 1ª pessoa) e dizer o
resultado. É o que o worker faz quando a pessoa envia a decisão: achar o dispositivo e explicar o resultado. Compara:
  1. classe majoritária;
  2. regras sobre a conclusão ("nego provimento", "dou parcial provimento", "não conheço"…);
  3. TF-IDF + regressão logística sobre a conclusão.

Erro grave: **provido ↔ desprovido** (a pessoa entende que ganhou quando perdeu, ou o contrário). Divisão por processo
(`classificador_tipo.divisao`). Saída: `treino/relatorios/resultado_pedido.{json,md}`.

Do recurso ao pedido: provido/desprovido é sobre o recurso; para virar procedente/improcedente do pedido é preciso
saber quem recorreu e o que a sentença decidiu. O mapeamento por regras está em `worker/modelos/resultado_pedido.py`
e precisa do rótulo-ouro por pedido para ser medido.
"""

from __future__ import annotations

import argparse
from collections import Counter

from treino.comum import RELATORIOS, salvar_json
from worker.modelos.resultado_pedido import classificar_regra, trecho_acordam, trecho_conclusao  # noqa: F401

CLASSES = ("provido", "parcialmente_provido", "desprovido", "nao_conhecido")
TROCAS_GRAVES = {("provido", "desprovido"), ("desprovido", "provido")}


def avaliar(y_true: list[str], y_pred: list[str | None]) -> dict:
    from treino.metricas import f1_por_classe

    y_pred = [p or "__abstencao__" for p in y_pred]
    por = f1_por_classe(y_true, y_pred, CLASSES)
    return {"acuracia": sum(a == b for a, b in zip(y_true, y_pred, strict=True)) / len(y_true),
            "f1_macro": sum(c["f1"] for c in por.values()) / len(CLASSES), "por_classe": por,
            "abstencoes": sum(p == "__abstencao__" for p in y_pred),
            "troca_grave": sum((a, b) in TROCAS_GRAVES for a, b in zip(y_true, y_pred, strict=True)),
            "matriz_confusao": {t: dict(Counter(p for tt, p in zip(y_true, y_pred, strict=True) if tt == t))
                                for t in CLASSES}}


# ---------------------------------------------------------------- execução
def montar(df) -> tuple[list[dict], Counter]:
    motivos: Counter = Counter()
    ex = []
    for processo, div, texto in zip(df.processo, df.divisao, df.texto_completo, strict=True):
        ac, conc = trecho_acordam(texto), trecho_conclusao(texto)
        if not ac:
            motivos["sem_acordam"] += 1
            continue
        rot = classificar_regra(ac)
        if rot is None:
            motivos["acordam_misto_ou_sem_formula"] += 1
            continue
        if not conc:
            motivos["sem_conclusao"] += 1
            continue
        motivos["usado"] += 1
        ex.append({"processo": processo, "divisao": div, "conclusao": conc[:3000], "rotulo": rot})
    return ex, motivos


def rodar(a) -> dict:
    import pandas as pd
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression

    from treino.classificador_tipo import baixar, divisao
    from treino.metricas import ece

    df = pd.read_parquet(baixar(), columns=["processo", "texto_integral"]).rename(columns={"texto_integral": "texto_completo"})
    df["divisao"] = df.processo.map(divisao)
    ex, motivos = montar(df)
    por_div = {d: [e for e in ex if e["divisao"] == d] for d in ("treino", "validacao", "teste")}
    dist = {d: dict(Counter(e["rotulo"] for e in v)) for d, v in por_div.items()}
    print(dict(motivos), dist, flush=True)
    res: dict[str, dict] = {}
    maj = Counter(e["rotulo"] for e in por_div["treino"]).most_common(1)[0][0]
    res["majoritaria"] = {d: avaliar([e["rotulo"] for e in v], [maj] * len(v)) for d, v in por_div.items() if d != "treino"}
    res["regras_conclusao"] = {d: avaliar([e["rotulo"] for e in v], [classificar_regra(e["conclusao"]) for e in v])
                               for d, v in por_div.items() if d != "treino"}
    vec = TfidfVectorizer(ngram_range=(1, 3), min_df=2, sublinear_tf=True, strip_accents="unicode", max_features=200_000)
    xtr = vec.fit_transform([e["conclusao"] for e in por_div["treino"]])
    lr = LogisticRegression(C=8.0, class_weight="balanced", max_iter=3000).fit(xtr, [e["rotulo"] for e in por_div["treino"]])
    res["tfidf_lr_conclusao"] = {}
    for d in ("validacao", "teste"):
        proba = lr.predict_proba(vec.transform([e["conclusao"] for e in por_div[d]]))
        pred = [lr.classes_[i] for i in proba.argmax(1)]
        m = avaliar([e["rotulo"] for e in por_div[d]], pred)
        m["ece"] = ece(list(proba.max(1)), [p == e["rotulo"] for p, e in zip(pred, por_div[d], strict=True)])
        res["tfidf_lr_conclusao"][d] = m
    rel = {"motivos": dict(motivos), "distribuicao": dist, "resultados": res,
           "rotulo": "prata — fórmula do ACORDAM; recurso, não pedido"}
    if not a.sem_mlflow:
        from treino.comum import iniciar_mlflow, tags_padrao

        mlflow = iniciar_mlflow("resultado_pedido")
        for nome, r in res.items():
            with mlflow.start_run(run_name=nome):
                mlflow.set_tags(tags_padrao(tarefa="resultado_recurso", variante=nome, rotulo=rel["rotulo"]))
                mlflow.log_param("variante", nome)
                for d in ("validacao", "teste"):
                    mlflow.log_metrics({f"{d}.f1_macro": r[d]["f1_macro"], f"{d}.troca_grave": r[d]["troca_grave"],
                                        f"{d}.abstencoes": r[d]["abstencoes"]})
    return rel


def markdown(rel: dict) -> str:
    lin = ["# Resultado: regras × modelo (resultado do recurso a partir da conclusão do voto)", "",
           f"Acórdãos usados/descartados: {rel['motivos']}. **Rótulo prata**: fórmula do ACORDAM, por recurso.", "",
           "| Variante | F1 macro | Acurácia | " + " | ".join(f"F1 {c}" for c in CLASSES) + " | Abstenções | "
           "Troca provido ↔ desprovido |", "|---|---:|---:|" + "---:|" * len(CLASSES) + "---:|---:|"]
    for nome, r in rel["resultados"].items():
        t = r["teste"]
        lin.append(f"| {nome} | {t['f1_macro']:.3f} | {t['acuracia']:.3f} | "
                   + " | ".join(f"{t['por_classe'][c]['f1']:.3f}" for c in CLASSES)
                   + f" | {t['abstencoes']} | {t['troca_grave']} |")
    lin += ["", "Teste = divisão congelada por hash do processo. A regra abstém quando a conclusão mistura resultados; "
            "o modelo nunca abstém (o limiar de abstenção é calibrado em `treino/calibracao.py`)."]
    return "\n".join(lin) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sem-mlflow", action="store_true")
    a = ap.parse_args()
    rel = rodar(a)
    salvar_json(rel, RELATORIOS / "resultado_pedido.json")
    (RELATORIOS / "resultado_pedido.md").write_text(markdown(rel), encoding="utf-8")
    print(markdown(rel))


if __name__ == "__main__":
    main()
