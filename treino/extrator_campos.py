"""Avaliação do extrator de campos por regras (issue #24, RF02) contra os metadados públicos do RepoJus (prata).

    uv run --group treino python -m treino.extrator_campos [--docs 5000]

Os metadados do tribunal (número do processo, relator, data do julgamento) servem de referência prata para os campos
que eles cobrem; os demais campos (partes, valores, pedidos) só têm **cobertura** medida até o rótulo-ouro do segundo
lote anotado (Eng. de dados + Cientista de dados, #15). Divisão por processo: só o teste é usado.

Métricas: acerto por campo (valor igual ao metadado, normalizado), cobertura (campo preenchido) e **campo inventado**
(preenchido e diferente do metadado), o erro que o RNF04 manda evitar.
Saída: `treino/relatorios/extrator_campos.{json,md}`.
"""
from __future__ import annotations

import argparse
import re
import unicodedata

from treino.comum import RELATORIOS, parametros, salvar_json

CAMPOS_REFERENCIA = {"numero_processo": "processo", "relator": "relator", "data_julgamento": "data_julgamento"}


def normalizar(campo: str, v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s or s.lower() in ("nan", "none", "nat"):
        return None
    if campo == "numero_processo":
        return re.sub(r"\D", "", s) or None
    if campo == "relator":
        s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).upper()
        return " ".join(re.sub(r"[^A-Z ]", " ", s).split()) or None
    if campo == "data_julgamento":
        return s[:10]
    return s


_LIGACOES = {"DE", "DA", "DO", "DOS", "DAS", "E"}


def relator_bate(previsto: str, ref: str) -> bool:
    """O texto às vezes traz parte do nome ou iniciais ("ANDRE R P V DAMASCENO" × "ANDRE RODRIGUES PEREIRA DA VEIGA
    DAMASCENO"): cada palavra prevista precisa estar no nome de referência, ou ser a inicial de uma delas."""
    p = [t for t in previsto.split() if t not in _LIGACOES]
    r = set(ref.split()) - _LIGACOES
    iniciais = {t[0] for t in r}
    bate = sum(t in r or (len(t) == 1 and t in iniciais) for t in p)
    return bool(p) and bate / len(p) >= 0.75 and any(len(t) > 1 and t in r for t in p)


def pontuar(campo: str, previsto: str | None, ref: str | None) -> str:
    """acerto | inventado | omitido | sem_referencia"""
    if ref is None:
        return "sem_referencia"
    if previsto is None:
        return "omitido"
    ok = relator_bate(previsto, ref) if campo == "relator" else previsto == ref
    return "acerto" if ok else "inventado"


def rodar(docs: int) -> dict:
    import pandas as pd

    from treino.classificador_tipo import baixar, divisao
    from worker.modelos.extrator_campos import como_dict, extrair

    df = pd.read_parquet(baixar(), columns=["processo", "relator", "data_julgamento", "texto_integral"])
    df = df[df.processo.map(divisao) == "teste"]
    if docs:
        df = df.sample(n=min(docs, len(df)), random_state=11)
    contagem: dict[str, dict[str, int]] = {}
    for _, linha in df.iterrows():
        prev = como_dict(extrair(linha.texto_integral))
        for campo, valor in prev.items():
            c = contagem.setdefault(campo, {"preenchido": 0, "acerto": 0, "inventado": 0, "omitido": 0, "sem_referencia": 0})
            c["preenchido"] += valor is not None
            if campo in CAMPOS_REFERENCIA:
                c[pontuar(campo, normalizar(campo, valor), normalizar(campo, linha[CAMPOS_REFERENCIA[campo]]))] += 1
    n = len(df)
    res = {}
    for campo, c in contagem.items():
        com_ref = c["acerto"] + c["inventado"] + c["omitido"]
        res[campo] = {"cobertura": c["preenchido"] / n, **c,
                      "acerto": c["acerto"] / com_ref if com_ref else None,
                      "inventado": c["inventado"] / com_ref if com_ref else None, "com_referencia": com_ref}
    return {"docs_teste": n, "referencia": "metadados RepoJus (prata)", "campos": res}


def markdown(rel: dict) -> str:
    lin = ["# Extrator de campos por regras — acórdãos do TRT-10 (teste)", "",
           f"{rel['docs_teste']} acórdãos da divisão de teste. Referência: {rel['referencia']}; campos sem metadado só "
           "têm cobertura. Nenhum nome de parte ou advogado é extraído (RNF01).", "",
           "| Campo | Cobertura | Acerto (com referência) | Inventado | Docs com referência |", "|---|---:|---:|---:|---:|"]
    for campo, r in rel["campos"].items():
        ac = f"{r['acerto']:.3f}" if r["acerto"] is not None else "—"
        inv = f"{r['inventado']:.3f}" if r["inventado"] is not None else "—"
        lin.append(f"| {campo} | {r['cobertura']:.1%} | {ac} | {inv} | {r['com_referencia'] or '—'} |")
    return "\n".join(lin) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--docs", type=int, default=parametros("extrator_campos").get("docs", 0),
                    help="amostra do teste (0 = todo o teste)")
    a = ap.parse_args()
    rel = rodar(a.docs)
    salvar_json(rel, RELATORIOS / "extrator_campos.json")
    (RELATORIOS / "extrator_campos.md").write_text(markdown(rel), encoding="utf-8")
    print(markdown(rel))


if __name__ == "__main__":
    main()
