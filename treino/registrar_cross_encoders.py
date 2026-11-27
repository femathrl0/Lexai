"""Registra o reranker, o verificador NLI e os embeddings no MLflow (issue #24): uma versão por (repositório, revisão).

    uv run --group treino python -m treino.registrar_cross_encoders [--sem-pesos]

Os pesos são do Hugging Face com revisão fixa; o registro guarda a **referência** (`referencia.json` com repo e
revisão) e as métricas do benchmark que justificam a escolha, como qualquer outro modelo (manual: "registrado como
qualquer outro modelo"). Com `--com-pesos` também guarda o snapshot dos pesos como artefato (para rodar sem o HF Hub).

Cada versão entra com alias `candidato` e tag `estagio=candidato`; a promoção é pelo `treino/promover.py`.
As versões fixadas em `worker/modelos/em_uso.yml` são o ponto de partida.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from treino.comum import RELATORIOS, iniciar_mlflow, tags_padrao

METRICAS = {
    "reranker": ("benchmark_rerankers.json", "resultados.reranker:{repo}.metricas.test"),
    "verificador_nli": ("benchmark_nli.json", "resultados.{repo}.validacao_completa.em_uso"),
}


def metricas_do_benchmark(nome: str, repo: str) -> dict:
    from treino.portao_regressao import extrair

    if nome not in METRICAS:
        return {}
    arquivo, caminho = METRICAS[nome]
    rel = RELATORIOS / arquivo
    if not rel.exists():
        return {}
    try:
        valores = extrair(json.loads(rel.read_text(encoding="utf-8")), caminho.format(repo=repo))
    except KeyError:
        return {}
    return {k: float(v) for k, v in valores.items() if isinstance(v, int | float)}


def registrar(nome: str, cfg: dict, com_pesos: bool) -> str:
    mlflow = iniciar_mlflow(f"registro_{nome}")
    from mlflow import MlflowClient

    with mlflow.start_run(run_name=f"{cfg['repo']}@{cfg['revisao'][:8]}") as run:
        mlflow.set_tags(tags_padrao(tarefa=nome, repo=cfg["repo"], revisao=cfg["revisao"]))
        mlflow.log_params({"repo": cfg["repo"], "revisao": cfg["revisao"], **{f"limiar.{k}": v for k, v in
                                                                              (cfg.get("limiares") or {}).items()}})
        if m := metricas_do_benchmark(nome, cfg["repo"]):
            mlflow.log_metrics({k.replace("@", "_at_"): v for k, v in m.items()})
        with tempfile.TemporaryDirectory() as d:
            ref = Path(d) / "referencia.json"
            ref.write_text(json.dumps({"repo": cfg["repo"], "revisao": cfg["revisao"]}, indent=2))
            mlflow.log_artifact(str(ref), artifact_path="modelo")
        if com_pesos:
            from huggingface_hub import snapshot_download

            mlflow.log_artifacts(snapshot_download(cfg["repo"], revision=cfg["revisao"]), artifact_path="modelo/pesos")
        cli = MlflowClient()
        try:
            cli.get_registered_model(nome)
        except Exception:  # noqa: BLE001 - primeiro registro deste modelo
            cli.create_registered_model(nome, description=f"{nome}: referência a pesos do Hugging Face com revisão fixa")
        # pesos de terceiros (não é um "logged model" do MLflow): a versão aponta para o artefato de referência
        mv = cli.create_model_version(nome, source=f"{run.info.artifact_uri}/modelo", run_id=run.info.run_id)
    for k, v in {"estagio": "candidato", "tipo": "hf", "repo": cfg["repo"], "revisao": cfg["revisao"],
                 "limiares": json.dumps(cfg.get("limiares") or {})}.items():
        cli.set_model_version_tag(nome, mv.version, k, v)
    cli.set_registered_model_alias(nome, "candidato", mv.version)
    return f"{nome} v{mv.version} ← {cfg['repo']}@{cfg['revisao'][:8]} (candidato)"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--com-pesos", action="store_true")
    ap.add_argument("--modelos", nargs="*", default=["reranker", "verificador_nli", "embeddings"])
    a = ap.parse_args()
    from worker.modelos.registro import FIXADOS

    for nome in a.modelos:
        print(registrar(nome, FIXADOS[nome], a.com_pesos))


if __name__ == "__main__":
    main()
