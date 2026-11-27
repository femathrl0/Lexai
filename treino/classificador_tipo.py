"""Baseline do classificador de tipo de documento e fase (issue #10, RF03): TF-IDF + regressão logística.

Dados (provisórios até o rótulo-ouro da Cientista de dados): acórdãos públicos do TRT-10 de 2024 no RepoJus
(efaraneda/repojus, CC BY 4.0, revisão fixa abaixo). O rótulo é a classe processual publicada pelo tribunal,
agrupada em cinco tipos; a fase (conhecimento × execução) sai da classe.

Atenção ao atalho: o cabeçalho do acórdão traz a classe por extenso ("PROCESSO nº … - RECURSO ORDINÁRIO").
Por isso há três comparações:
  1. regras sobre o cabeçalho (baseline de regras);
  2. TF-IDF + LR no texto completo;
  3. TF-IDF + LR com o cabeçalho removido e o nome das classes mascarado — mede se o modelo entende o
     conteúdo, que é o que importa para documento sem cabeçalho (sentença, foto, trecho colado).

Divisão por processo (hash estável do número do processo), nunca por documento: embargos e recurso do mesmo
processo ficam na mesma divisão.

Uso:
    python -m treino.classificador_tipo baixar          # baixa o lote (não entra no Git)
    python -m treino.classificador_tipo treinar         # treina, avalia e registra no MLflow
"""

from __future__ import annotations

import argparse
import hashlib
import re
import urllib.request
from collections import Counter
from pathlib import Path

from treino.comum import RAIZ, RELATORIOS, parametros, salvar_json
from worker.modelos.tipo_documento import (  # noqa: F401 - reexportados: regras e pré-processamento vivem no worker
    CLASSES,
    FASE_DO_TIPO,
    MAX_CARACTERES,
    regra_cabecalho,
    sem_cabecalho,
)

REPOJUS_REVISAO = "91aa953b3c976a8688135dea49cf6644f7732243"
LOTE = {
    "id": "repojus-trt10-2024",
    "url": "https://huggingface.co/datasets/efaraneda/repojus/resolve/"
    f"{REPOJUS_REVISAO}/data/v3/p_tribunal=TRT10/p_ano=2024/part-00000.parquet",
    "caminho": RAIZ / "dados" / "raw" / "repojus" / "trt10_2024.parquet",
    "sha256": "453efb25ce420dbb34b78cccb1fd849d84bc76a40505febc03290e8ff1be6505",
    "licenca": "CC BY 4.0",
}
# O mesmo arquivo baixado pela ingestão de jurisprudência (Eng. de dados), no layout particionado do RepoJus.
CAMINHOS_ALTERNATIVOS = (
    RAIZ / "dados" / "raw" / "jurisprudencia" / "repojus" / "p_tribunal=TRT10_p_ano=2024_part-00000.parquet",
)

SEMENTE = parametros("dados").get("divisao_semente", "lexai-divisao-v1")

# classe processual do tribunal -> (tipo, fase). Fora do mapa = descartado (rótulo genérico ou raro demais).
MAPA_CLASSE: dict[str, tuple[str, str | None]] = {
    "Recurso Ordinário Trabalhista": ("recurso_ordinario", "conhecimento"),
    "Recurso Ordinário - Rito Sumaríssimo": ("recurso_ordinario", "conhecimento"),
    "Remessa Necessária / Recurso Ordinário": ("recurso_ordinario", "conhecimento"),
    "Remessa Necessária Trabalhista": ("recurso_ordinario", "conhecimento"),
    "Agravo de Petição": ("agravo_peticao", "execucao"),
    "Embargos de Declaração Cível": ("embargos_declaracao", None),
    "Agravo de Instrumento em Recurso Ordinário": ("agravo_instrumento", "conhecimento"),
    "Agravo de Instrumento em Agravo de Petição": ("agravo_instrumento", "execucao"),
    "Mandado de Segurança Cível": ("acao_originaria", None),
    "Ação Rescisória": ("acao_originaria", None),
    "Habeas Corpus Cível": ("acao_originaria", None),
    "Conflito de competência cível": ("acao_originaria", None),
    "Tutela Cautelar Antecedente": ("acao_originaria", None),
    "Tutela Antecipada Antecedente": ("acao_originaria", None),
    "Dissídio Coletivo": ("acao_originaria", None),
    "Dissídio Coletivo de Greve": ("acao_originaria", None),
    "Ação Anulatória de Cláusulas Convencionais": ("acao_originaria", None),
    "Petição Cível": ("acao_originaria", None),
    "Exceção de Suspeição": ("acao_originaria", None),
    "Reclamação": ("acao_originaria", None),
}
def rotular(classe_tribunal: str) -> tuple[str, str | None] | None:
    return MAPA_CLASSE.get(classe_tribunal.strip())


def divisao(processo: str, semente: str = SEMENTE) -> str:
    """treino (70%) / validacao (15%) / teste (15%) por hash estável do processo."""
    num = re.sub(r"\D", "", processo) or processo
    b = int(hashlib.sha256(f"{semente}:{num}".encode()).hexdigest(), 16) % 100
    return "treino" if b < 70 else "validacao" if b < 85 else "teste"


def corrigir_rotulo(classe: str, texto: str) -> tuple[str, bool]:
    """O metadado do tribunal rotula o acórdão de embargos de declaração pela classe do recurso embargado
    (~10% dos "recursos ordinários" de 2024 são, pelo cabeçalho, julgamento de embargos). Quando o cabeçalho diz
    explicitamente que é embargos, o tipo do documento é embargos. Devolve (classe, corrigido?)."""
    if classe != "embargos_declaracao" and regra_cabecalho(texto) == "embargos_declaracao":
        return "embargos_declaracao", True
    return classe, False


# ---------------------------------------------------------------- dados
def baixar() -> Path:
    from treino.comum import sha256_arquivo

    destino: Path = LOTE["caminho"]
    if not destino.exists():
        destino = next((c for c in CAMINHOS_ALTERNATIVOS if c.exists()), destino)
    if not destino.exists():
        destino.parent.mkdir(parents=True, exist_ok=True)
        print(f"baixando {LOTE['url']}")
        urllib.request.urlretrieve(LOTE["url"], destino)
    h = sha256_arquivo(destino)
    if h != LOTE["sha256"]:
        raise SystemExit(f"hash inesperado para {destino}: {h}")
    return destino


def carregar_lote():
    import pandas as pd

    df = pd.read_parquet(baixar(), columns=["doc_id", "processo", "tipo", "texto_integral"])
    from treino.esquemas import validar

    validar("repojus", df)  # lote fora do esquema para o pipeline antes do treino
    rot = df["tipo"].map(rotular)
    df = df[rot.notna()].copy()
    df["classe"] = rot[rot.notna()].map(lambda x: x[0])
    # a fase vem do recurso de origem, inclusive nos embargos corrigidos
    # (ED em RO = conhecimento; ED em AP = execução)
    df["fase"] = rot[rot.notna()].map(lambda x: x[1])
    df["divisao"] = df["processo"].map(divisao)
    df["texto"] = df["texto_integral"].str.slice(0, MAX_CARACTERES)
    corr = [corrigir_rotulo(c, t) for c, t in zip(df["classe"], df["texto"], strict=True)]
    df["classe_tribunal"] = df["classe"]
    df["classe"] = [c for c, _ in corr]
    df["rotulo_corrigido"] = [x for _, x in corr]
    return df.drop(columns=["texto_integral"]).reset_index(drop=True)


# ---------------------------------------------------------------- avaliação
def avaliar(y_true, y_pred, confianca=None, fase_true=None) -> dict:
    from treino.metricas import ece, f1_por_classe

    y_pred = [p if p is not None else "__abstencao__" for p in y_pred]
    por_classe = f1_por_classe(y_true, y_pred, CLASSES)
    res = {
        "acuracia": sum(t == p for t, p in zip(y_true, y_pred, strict=True)) / len(y_true),
        "f1_macro": sum(c["f1"] for c in por_classe.values()) / len(CLASSES),
        "por_classe": por_classe,
        "abstencoes": sum(p == "__abstencao__" for p in y_pred),
        "matriz_confusao": {
            t: dict(Counter(p for tt, p in zip(y_true, y_pred, strict=True) if tt == t)) for t in CLASSES
        },
    }
    if fase_true is not None:
        # o erro que importa em fase: execução lida como conhecimento ou vice-versa
        pares = [(f, FASE_DO_TIPO.get(p)) for f, p in zip(fase_true, y_pred, strict=True) if f is not None]
        res["fase_acuracia"] = sum(f == p for f, p in pares) / len(pares) if pares else None
        res["fase_trocada"] = sum(1 for f, p in pares if p is not None and p != f)
        res["fase_abstencao"] = sum(1 for _, p in pares if p is None)
    if confianca is not None:
        res["ece"] = ece(list(confianca), [t == p for t, p in zip(y_true, y_pred, strict=True)])
    return res


def treinar(args) -> None:
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline

    from treino.comum import iniciar_mlflow, tags_padrao
    from treino.metricas import limiar_abstencao

    df = carregar_lote()
    partes = {d: df[df.divisao == d] for d in ("treino", "validacao", "teste")}
    vazamento = set(partes["treino"].processo) & (set(partes["validacao"].processo) | set(partes["teste"].processo))
    assert not vazamento, f"processo em mais de uma divisão: {list(vazamento)[:3]}"
    dist = {d: p.classe.value_counts().to_dict() for d, p in partes.items()}
    correcoes = {k: int(v) for k, v in df.groupby("classe_tribunal").rotulo_corrigido.sum().items() if v}
    print("distribuição:", dist, "\nrótulos corrigidos para embargos:", correcoes)

    mlflow = None if args.sem_mlflow else iniciar_mlflow("classificador_tipo_fase")
    dados_tags = {
        "dados.lote": LOTE["id"],
        "dados.sha256": LOTE["sha256"],
        "dados.repojus_revisao": REPOJUS_REVISAO,
        "dados.semente_divisao": SEMENTE,
        "dados.provisorio": "sim — aguarda rótulo-ouro da Cientista de dados",
    }
    resultados: dict[str, dict] = {}

    def registrar(nome: str, params: dict, metricas: dict, modelo=None):
        resultados[nome] = {"params": params, **metricas}
        if not mlflow:
            return None
        with mlflow.start_run(run_name=nome) as run:
            mlflow.set_tags(tags_padrao(tarefa="tipo_documento", variante=nome, **dados_tags))
            mlflow.log_params(params)
            for div, m in metricas.items():
                if not isinstance(m, dict):
                    continue
                mlflow.log_metrics(
                    {f"{div}.{k}": float(v) for k, v in m.items() if isinstance(v, int | float) and v is not None}
                )
                for c, mc in m.get("por_classe", {}).items():
                    mlflow.log_metric(f"{div}.f1.{c}", mc["f1"])
            mlflow.log_dict(metricas, "metricas.json")
            mlflow.log_dict(dist, "distribuicao.json")
            if modelo is not None:
                from mlflow import sklearn as mlflow_sklearn

                mlflow_sklearn.log_model(modelo, artifact_path="modelo")
            return run.info.run_id

    # 1. classe majoritária
    maj = partes["treino"].classe.mode()[0]
    registrar(
        "majoritaria",
        {"classe": maj},
        {
            d: avaliar(list(p.classe), [maj] * len(p), fase_true=list(p.fase))
            for d, p in partes.items()
            if d != "treino"
        },
    )

    # 2. regras no cabeçalho
    registrar(
        "regras_cabecalho",
        {"fonte": "linha PROCESSO nº … - CLASSE"},
        {
            d: avaliar(list(p.classe), [regra_cabecalho(t) for t in p.texto], fase_true=list(p.fase))
            for d, p in partes.items()
            if d != "treino"
        },
    )

    # 3 e 4. TF-IDF + LR, com e sem cabeçalho
    run_ids = {}
    modelos = {}
    for variante, prep in (("tfidf_lr_texto_completo", None), ("tfidf_lr_sem_cabecalho", sem_cabecalho)):
        X = {d: (p.texto.map(prep) if prep else p.texto).tolist() for d, p in partes.items()}
        melhor = None
        for C in args.C:
            pipe = Pipeline(
                [
                    (
                        "tfidf",
                        TfidfVectorizer(
                            ngram_range=(1, 2),
                            min_df=3,
                            max_df=0.9,
                            sublinear_tf=True,
                            max_features=args.max_features,
                            strip_accents="unicode",
                            lowercase=True,
                        ),
                    ),
                    ("lr", LogisticRegression(C=C, class_weight="balanced", max_iter=3000)),
                ]
            )
            pipe.fit(X["treino"], partes["treino"].classe)
            f1 = avaliar(list(partes["validacao"].classe), list(pipe.predict(X["validacao"])))["f1_macro"]
            print(f"  {variante} C={C}: F1 macro validação {f1:.4f}", flush=True)
            if melhor is None or f1 > melhor[0]:
                melhor = (f1, C, pipe)
        _, C, pipe = melhor
        # limiar de abstenção escolhido na validação (RNF04), aplicado no teste
        proba_val = pipe.predict_proba(X["validacao"])
        pred_val = pipe.classes_[np.argmax(proba_val, axis=1)]
        conf_val = proba_val.max(axis=1)
        limiar, prec_aceitas, cobertura = limiar_abstencao(
            list(conf_val),
            [a == b for a, b in zip(pred_val, partes["validacao"].classe, strict=True)],
            args.precisao_alvo,
        )
        metricas = {}
        for d in ("validacao", "teste"):
            proba = pipe.predict_proba(X[d])
            pred = pipe.classes_[np.argmax(proba, axis=1)]
            conf = proba.max(axis=1)
            m = avaliar(list(partes[d].classe), list(pred), confianca=list(conf), fase_true=list(partes[d].fase))
            aceitas = conf >= limiar
            m["com_abstencao"] = {
                "limiar": float(limiar),
                "cobertura": float(aceitas.mean()),
                "acuracia_aceitas": float((pred[aceitas] == partes[d].classe.to_numpy()[aceitas]).mean())
                if aceitas.any()
                else None,
            }
            metricas[d] = m
        params = {
            "C": C,
            "ngram": "1-2",
            "min_df": 3,
            "max_df": 0.9,
            "max_features": args.max_features,
            "class_weight": "balanced",
            "max_caracteres": MAX_CARACTERES,
            "precisao_alvo_abstencao": args.precisao_alvo,
            "limiar_abstencao": float(limiar),
            "preprocessamento": variante,
        }
        run_ids[variante] = registrar(variante, params, metricas, modelo=pipe)
        modelos[variante] = pipe
        print(
            f"  {variante}: teste F1 macro {metricas['teste']['f1_macro']:.4f}, limiar {limiar:.3f} "
            f"(cobertura val {cobertura:.2%}, precisão aceitas {prec_aceitas:.2%})",
            flush=True,
        )

    # candidato: a variante sem cabeçalho (generaliza para documento sem a linha de classe); vai como "candidato",
    # nunca "em-uso" — promoção só com Eng. de ML + Curadoria.
    if mlflow and run_ids.get("tfidf_lr_sem_cabecalho"):
        from mlflow import MlflowClient

        mv = mlflow.register_model(f"runs:/{run_ids['tfidf_lr_sem_cabecalho']}/modelo", "classificador_tipo_fase")
        cli = MlflowClient()
        cli.set_registered_model_alias("classificador_tipo_fase", "candidato", mv.version)
        cli.set_model_version_tag("classificador_tipo_fase", mv.version, "estagio", "candidato")
        resultados["registro"] = {"modelo": "classificador_tipo_fase", "versao": mv.version, "alias": "candidato"}
        print(f"registrado classificador_tipo_fase v{mv.version} (alias candidato)")

    resumo = {
        "lote": {k: str(v) for k, v in LOTE.items()},
        "semente": SEMENTE,
        "distribuicao": dist,
        "rotulos_corrigidos_para_embargos": correcoes,
        "resultados": resultados,
    }
    salvar_json(resumo, RELATORIOS / "classificador_tipo_baseline.json")
    (RELATORIOS / "classificador_tipo_baseline.md").write_text(_md(resumo), encoding="utf-8")
    print(f"relatório: {RELATORIOS / 'classificador_tipo_baseline.md'}")


def _md(r: dict) -> str:
    res = r["resultados"]
    lin = [
        "# Baseline do classificador de tipo de documento e fase",
        "",
        f"Lote **{r['lote']['id']}** (RepoJus, revisão `{REPOJUS_REVISAO[:10]}`, "
        f"sha256 `{r['lote']['sha256'][:12]}…`, "
        f"{r['lote']['licenca']}). Divisão por processo, semente `{r['semente']}`. **Rótulos provisórios**: classe "
        "processual publicada pelo tribunal, até o rótulo-ouro da Cientista de dados.",
        "",
        "| Divisão | " + " | ".join(CLASSES) + " |",
        "|---|" + "---:|" * len(CLASSES),
    ]
    for d, cont in r["distribuicao"].items():
        lin.append(f"| {d} | " + " | ".join(str(cont.get(c, 0)) for c in CLASSES) + " |")
    corr = r.get("rotulos_corrigidos_para_embargos", {})
    if corr:
        lin += [
            "",
            f"Rótulos corrigidos para `embargos_declaracao` pelo cabeçalho (metadado do tribunal usa a classe do "
            f"recurso embargado): {', '.join(f'{k}: {v}' for k, v in corr.items())}. A variante `regras_cabecalho` "
            "fica parcialmente circular nessa classe.",
        ]
    lin += [
        "",
        "## Teste (divisão congelada por hash do processo)",
        "",
        "| Variante | Acurácia | F1 macro | "
        + " | ".join(f"F1 {c}" for c in CLASSES)
        + " | Fase: acurácia | Fase trocada | ECE | Abstenção: cobertura / acurácia |",
        "|---|---:|---:|" + "---:|" * len(CLASSES) + "---:|---:|---:|---|",
    ]
    for nome in ("majoritaria", "regras_cabecalho", "tfidf_lr_texto_completo", "tfidf_lr_sem_cabecalho"):
        if nome not in res:
            continue
        t = res[nome]["teste"]
        ab = t.get("com_abstencao")
        ab_txt = f"{ab['cobertura']:.1%} / {ab['acuracia_aceitas']:.2%} (limiar {ab['limiar']:.2f})" if ab else "—"
        ece_txt = f"{t['ece']:.3f}" if "ece" in t else "—"
        fase = f"{t['fase_acuracia']:.3f}" if t.get("fase_acuracia") is not None else "—"
        lin.append(
            f"| {nome} | {t['acuracia']:.3f} | {t['f1_macro']:.3f} | "
            + " | ".join(f"{t['por_classe'][c]['f1']:.3f}" for c in CLASSES)
            + f" | {fase} | {t.get('fase_trocada', '—')} | {ece_txt} | {ab_txt} |"
        )
    if "tfidf_lr_sem_cabecalho" in res:
        mc = res["tfidf_lr_sem_cabecalho"]["teste"]["matriz_confusao"]
        cols = list(CLASSES) + ["__abstencao__"]
        lin += [
            "",
            "## Matriz de confusão — tfidf_lr_sem_cabecalho, teste (linha = verdadeiro)",
            "",
            "| | " + " | ".join(c for c in CLASSES) + " |",
            "|---|" + "---:|" * len(CLASSES),
        ]
        for t_ in CLASSES:
            lin.append(f"| {t_} | " + " | ".join(str(mc.get(t_, {}).get(c, 0)) for c in cols[:-1]) + " |")
    if "registro" in res:
        reg = res["registro"]
        lin += ["", f"Registrado no MLflow como `{reg['modelo']}` v{reg['versao']}, alias `{reg['alias']}`."]
    return "\n".join(lin) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("baixar")
    t = sub.add_parser("treinar")
    p = parametros("classificador_tipo")
    t.add_argument("--C", type=float, nargs="+", default=p.get("C", [1.0, 4.0, 16.0]))
    t.add_argument("--max-features", type=int, default=p.get("max_features", 300_000))
    t.add_argument("--precisao-alvo", type=float, default=p.get("precisao_alvo", 0.98),
                   help="acurácia mínima nas previsões aceitas")
    t.add_argument("--sem-mlflow", action="store_true")
    a = ap.parse_args()
    if a.cmd == "baixar":
        print(baixar())
    else:
        treinar(a)


if __name__ == "__main__":
    main()
