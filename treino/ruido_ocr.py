"""Robustez a ruído de OCR (issue #31, bloqueio da #30): queda de cada componente em uso do texto nativo ao texto com
erros típicos de OCR.

    uv run --group treino python -m treino.ruido_ocr [--docs 2000] [--taxas 0 0.02 0.05 0.1]

Enquanto o conjunto de fotos do grupo não existe (#29), o ruído é **sintético** e calibrado pelos erros mais comuns
de OCR em português: troca de letras parecidas (rn↔m, l↔1, O↔0, e↔c), acento perdido, letra apagada ou duplicada,
palavras coladas e quebra de linha com hífen. A taxa é por caractere. Mede, nos acórdãos de teste:

- tipo do documento por regras do cabeçalho (acerto e abstenção);
- resultado do recurso por regras da conclusão (acerto e troca provido ↔ desprovido);
- extrator: número do processo e relator.

Limite proposto para o portão #35: **queda ≤ 5 pontos** com 5% de ruído, sem aumento de troca grave. Se um componente
passar do limite, o próximo passo é treinar com aumento de ruído e medir o ganho (regra 0004).
Saída: `treino/relatorios/ruido_ocr.{json,md}`.
"""
from __future__ import annotations

import argparse
import random
import unicodedata

from treino.comum import RELATORIOS, salvar_json

PARECIDAS = {"m": "rn", "rn": "m", "l": "1", "1": "l", "O": "0", "0": "O", "e": "c", "c": "e", "i": "í", "S": "5", "5": "S",
             "B": "8", "g": "q", "h": "b", "u": "ii", "ç": "c", "ã": "a", "õ": "o"}
LIMITE_QUEDA = 0.05


# ---------------------------------------------------------------- funções puras (testadas no CI)
def ruido(texto: str, taxa: float, semente: int = 0) -> str:
    """Erros de OCR sintéticos com probabilidade `taxa` por caractere (determinístico pela semente)."""
    if taxa <= 0:
        return texto
    rng = random.Random(semente)
    out: list[str] = []
    i = 0
    while i < len(texto):
        c = texto[i]
        if c.isspace() or rng.random() >= taxa:
            out.append(c)
            i += 1
            continue
        r = rng.random()
        if texto[i:i + 2] in PARECIDAS and r < 0.2:
            out.append(PARECIDAS[texto[i:i + 2]])
            i += 2
            continue
        if r < 0.45 and c in PARECIDAS:
            out.append(PARECIDAS[c])
        elif r < 0.6:
            out.append("".join(x for x in unicodedata.normalize("NFKD", c) if not unicodedata.combining(x)))
        elif r < 0.72:
            pass  # letra apagada
        elif r < 0.82:
            out.append(c + c)
        elif r < 0.92 and i + 1 < len(texto) and texto[i + 1] == " ":
            out.append(c)
            i += 1  # palavras coladas
        else:
            out.append(c + "-\n")
        i += 1
    return "".join(out)


def queda(nativo: float, com_ruido: float) -> float:
    return round(nativo - com_ruido, 4)


# ---------------------------------------------------------------- execução
def rodar(docs: int, taxas: list[float]) -> dict:
    import pandas as pd

    from treino.classificador_tipo import baixar, carregar_lote
    from treino.extrator_campos import normalizar, pontuar
    from treino.resultado_pedido import TROCAS_GRAVES
    from worker.modelos.extrator_campos import numero_processo, relator
    from worker.modelos.resultado_pedido import classificar_regra, trecho_acordam, trecho_conclusao
    from worker.modelos.tipo_documento import regra_cabecalho

    df = carregar_lote()
    df = df[df.divisao == "teste"].sample(n=min(docs, int((df.divisao == "teste").sum())), random_state=21)
    # texto completo (o lote do classificador corta em 30 mil caracteres e perde a conclusão dos acórdãos longos)
    meta = pd.read_parquet(baixar(), columns=["doc_id", "relator", "texto_integral"]).set_index("doc_id")
    df = df.join(meta, on="doc_id")
    res = {}
    for taxa in taxas:
        tipo_ok = tipo_abst = res_ok = res_n = trocas = proc_ok = rel_ok = 0
        for k, linha in enumerate(df.itertuples()):
            t = ruido(linha.texto_integral, taxa, semente=k)
            prev = regra_cabecalho(t)
            tipo_ok += prev == linha.classe
            tipo_abst += prev is None
            ac = trecho_acordam(linha.texto_integral)
            rot = classificar_regra(ac) if ac else None
            conc = trecho_conclusao(t)
            if rot:
                p = classificar_regra(conc) if conc else None
                res_n += 1
                res_ok += p == rot
                trocas += (rot, p) in TROCAS_GRAVES
            proc_ok += pontuar("numero_processo", normalizar("numero_processo", numero_processo(t)),
                               normalizar("numero_processo", linha.processo)) == "acerto"
            rel_ok += pontuar("relator", normalizar("relator", relator(t)), normalizar("relator", linha.relator)) == "acerto"
        n = len(df)
        res[str(taxa)] = {"tipo_acerto": tipo_ok / n, "tipo_abstencao": tipo_abst / n,
                          "resultado_acerto": res_ok / max(res_n, 1), "resultado_troca_grave": trocas,
                          "processo_acerto": proc_ok / n, "relator_acerto": rel_ok / n}
        print(taxa, res[str(taxa)], flush=True)
    base = res[str(taxas[0])]
    for taxa in taxas[1:]:
        r = res[str(taxa)]
        r["queda"] = {k: queda(base[k], r[k]) for k in ("tipo_acerto", "resultado_acerto", "processo_acerto", "relator_acerto")}
        r["dentro_do_limite"] = all(v <= LIMITE_QUEDA for v in r["queda"].values()) and \
            r["resultado_troca_grave"] <= base["resultado_troca_grave"]
    return {"docs": len(df), "taxas": taxas, "limite_queda": LIMITE_QUEDA, "resultados": res,
            "ruido": "sintético (aguarda o conjunto de fotos do grupo, #29)"}


def aumento_resultado(taxas: list[float], max_treino: int = 6000) -> dict:
    """Ajuste com ruído (#31): TF-IDF de caracteres + LR no fim do acórdão (onde fica o dispositivo), treinado com
    ruído sorteado em {0, 2%, 5%}, contra as regras no mesmo texto ruidoso. Rótulo: fórmula do ACORDAM no texto limpo."""
    import pandas as pd
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression

    from treino.classificador_tipo import baixar, divisao
    from treino.resultado_pedido import TROCAS_GRAVES
    from worker.modelos.resultado_pedido import classificar_regra, trecho_acordam

    df = pd.read_parquet(baixar(), columns=["processo", "texto_integral"])
    df["divisao"] = df.processo.map(divisao)
    df["rotulo"] = [classificar_regra(a) if (a := trecho_acordam(t)) else None for t in df.texto_integral]
    df = df[df.rotulo.notna()]
    df["fim"] = df.texto_integral.str.slice(-3000)
    tr = df[df.divisao == "treino"].sample(n=min(max_treino, int((df.divisao == "treino").sum())), random_state=3)
    te = df[df.divisao == "teste"].sample(n=min(1500, int((df.divisao == "teste").sum())), random_state=4)
    rng = random.Random(5)
    x_tr = [ruido(t, rng.choice((0.0, 0.02, 0.05)), semente=i) for i, t in enumerate(tr.fim)]
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=3, sublinear_tf=True, max_features=300_000)
    lr = LogisticRegression(C=4, class_weight="balanced", max_iter=3000).fit(vec.fit_transform(x_tr), list(tr.rotulo))
    out = {}
    for taxa in taxas:
        x = [ruido(t, taxa, semente=10_000 + i) for i, t in enumerate(te.fim)]
        regras = [classificar_regra(t) for t in x]
        modelo = list(lr.predict(vec.transform(x)))
        y = list(te.rotulo)
        out[str(taxa)] = {v: {"acerto": sum(a == b for a, b in zip(y, p, strict=True)) / len(y),
                              "troca_grave": sum((a, b) in TROCAS_GRAVES for a, b in zip(y, p, strict=True))}
                          for v, p in (("regras", regras), ("char_tfidf_lr_aumento", modelo))}
        print("aumento", taxa, out[str(taxa)], flush=True)
    return {"treino": len(tr), "teste": len(te), "resultados": out}


def markdown(rel: dict) -> str:
    lin = ["# Robustez a ruído de OCR (sintético) — componentes em uso", "",
           f"{rel['docs']} acórdãos de teste. Ruído {rel['ruido']}. Limite proposto: queda ≤ {rel['limite_queda']:.0%}.", "",
           "| Ruído por caractere | Tipo (acerto) | Tipo (abstenção) | Resultado (acerto) | Troca grave | Processo | Relator "
           "| Dentro do limite |", "|---:|---:|---:|---:|---:|---:|---:|---|"]
    for taxa, r in rel["resultados"].items():
        ok = "—" if "dentro_do_limite" not in r else ("sim" if r["dentro_do_limite"] else "**não**")
        lin.append(f"| {float(taxa):.0%} | {r['tipo_acerto']:.3f} | {r['tipo_abstencao']:.3f} | {r['resultado_acerto']:.3f} | "
                   f"{r['resultado_troca_grave']} | {r['processo_acerto']:.3f} | {r['relator_acerto']:.3f} | {ok} |")
    if "aumento_resultado" in rel:
        au = rel["aumento_resultado"]
        lin += ["", "## Ajuste com ruído — resultado do recurso no fim do acórdão", "",
                f"TF-IDF de caracteres + LR treinado com ruído sorteado em {{0, 2%, 5%}} ({au['treino']} acórdãos de treino, "
                f"{au['teste']} de teste), contra as regras no mesmo texto ruidoso.", "",
                "| Ruído | Regras (acerto / troca grave) | Modelo com aumento (acerto / troca grave) |", "|---:|---|---|"]
        for taxa, r in au["resultados"].items():
            a, b = r["regras"], r["char_tfidf_lr_aumento"]
            lin.append(f"| {float(taxa):.0%} | {a['acerto']:.3f} / {a['troca_grave']} | {b['acerto']:.3f} / {b['troca_grave']} |")
    return "\n".join(lin) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--docs", type=int, default=2000)
    ap.add_argument("--taxas", type=float, nargs="+", default=[0.0, 0.02, 0.05, 0.10])
    ap.add_argument("--sem-aumento", action="store_true", help="não treina o modelo com aumento de ruído")
    a = ap.parse_args()
    rel = rodar(a.docs, a.taxas)
    if not a.sem_aumento:
        rel["aumento_resultado"] = aumento_resultado(a.taxas)
    salvar_json(rel, RELATORIOS / "ruido_ocr.json")
    (RELATORIOS / "ruido_ocr.md").write_text(markdown(rel), encoding="utf-8")
    print(markdown(rel))


if __name__ == "__main__":
    main()
