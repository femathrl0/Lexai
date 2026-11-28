"""Promoção e rollback de modelos no registro do MLflow (manual: "Só o Eng. de ML e a Curadoria, juntos, promovem").

    python -m treino.promover classificador_tipo_fase 3 --para aprovado --por "Felipe"
    python -m treino.promover classificador_tipo_fase 3 --para em-uso --por "Felipe" --curadoria "Laisa, 27/11"
    python -m treino.promover classificador_tipo_fase --rollback --por "Felipe" --motivo "regressão na demo"

Regras:
- `candidato → aprovado`: a versão passa no portão de regressão (`treino/portao_regressao.py`) com o relatório dela.
- `aprovado → em-uso`: exige a versão já `aprovado` **e** o registro da aprovação da Curadoria (`--curadoria`).
  A versão que estava em uso ganha o alias `anterior` (para o rollback) e a tag `estagio=historico`.
- `--rollback`: devolve o alias `em-uso` para a versão `anterior`.

Toda mudança vira uma linha em `docs/changelog_modelos.md` (manual: changelog para toda versão promovida). Depois de
promover, atualizar `worker/modelos/em_uso.yml` (fixado para quando o MLflow não está no ar) e a referência do portão
`treino/portoes/linha_base.json` no mesmo PR.
"""
from __future__ import annotations

import argparse
from datetime import datetime

from treino.comum import RAIZ

CHANGELOG = RAIZ / "docs" / "changelog_modelos.md"
ESTAGIOS = ("candidato", "aprovado", "em-uso")


class PromocaoInvalida(RuntimeError):
    pass


def _alias(cliente, nome: str, alias: str):
    try:
        return cliente.get_model_version_by_alias(nome, alias)
    except Exception:  # noqa: BLE001 - alias inexistente
        return None


def registrar_changelog(linha: str, caminho=CHANGELOG) -> None:
    if not caminho.exists():
        caminho.write_text("# Changelog de modelos\n\nUma linha por promoção ou rollback (`treino/promover.py`).\n\n"
                           "| Quando | Modelo | Versão | Mudança | Por | Curadoria | Motivo |\n"
                           "|---|---|---|---|---|---|---|\n", encoding="utf-8")
    with caminho.open("a", encoding="utf-8") as f:
        f.write(linha + "\n")


def promover(cliente, nome: str, versao: str, para: str, por: str, curadoria: str | None = None,
             motivo: str = "", changelog=CHANGELOG) -> str:
    if para not in ESTAGIOS:
        raise PromocaoInvalida(f"estágio desconhecido: {para}")
    mv = cliente.get_model_version(nome, versao)
    estagio = (mv.tags or {}).get("estagio", "candidato")
    if para == "em-uso":
        if estagio != "aprovado":
            raise PromocaoInvalida(f"{nome} v{versao} está em '{estagio}': só versão 'aprovado' vai para em-uso")
        if not curadoria:
            raise PromocaoInvalida("em-uso exige o registro da aprovação da Curadoria (--curadoria)")
        atual = _alias(cliente, nome, "em-uso")
        if atual is not None and str(atual.version) != str(versao):
            cliente.set_registered_model_alias(nome, "anterior", atual.version)
            cliente.set_model_version_tag(nome, atual.version, "estagio", "historico")
        cliente.set_model_version_tag(nome, versao, "aprovado_por_curadoria", curadoria)
    cliente.set_registered_model_alias(nome, para, versao)
    cliente.set_model_version_tag(nome, versao, "estagio", para)
    quando = datetime.now().strftime("%Y-%m-%d %H:%M")
    registrar_changelog(f"| {quando} | {nome} | v{versao} | {estagio} → {para} | {por} | {curadoria or '—'} | {motivo or '—'} |",
                        changelog)
    return f"{nome} v{versao}: {estagio} → {para}"


def rollback(cliente, nome: str, por: str, motivo: str, changelog=CHANGELOG) -> str:
    anterior = _alias(cliente, nome, "anterior")
    atual = _alias(cliente, nome, "em-uso")
    if anterior is None:
        raise PromocaoInvalida(f"{nome} não tem versão 'anterior' para rollback")
    cliente.set_registered_model_alias(nome, "em-uso", anterior.version)
    cliente.set_model_version_tag(nome, anterior.version, "estagio", "em-uso")
    if atual is not None:
        cliente.set_model_version_tag(nome, atual.version, "estagio", "historico")
        cliente.delete_registered_model_alias(nome, "anterior")
    quando = datetime.now().strftime("%Y-%m-%d %H:%M")
    de = f"v{atual.version}" if atual is not None else "—"
    registrar_changelog(f"| {quando} | {nome} | v{anterior.version} | rollback ({de} → v{anterior.version}) | {por} | — | "
                        f"{motivo} |", changelog)
    return f"{nome}: em-uso volta para v{anterior.version}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("modelo")
    ap.add_argument("versao", nargs="?")
    ap.add_argument("--para", choices=ESTAGIOS)
    ap.add_argument("--rollback", action="store_true")
    ap.add_argument("--por", required=True)
    ap.add_argument("--curadoria")
    ap.add_argument("--motivo", default="")
    a = ap.parse_args()
    from mlflow import MlflowClient

    from treino.comum import iniciar_mlflow

    iniciar_mlflow("promocoes")
    cliente = MlflowClient()
    if a.rollback:
        print(rollback(cliente, a.modelo, a.por, a.motivo or "rollback"))
    else:
        if not (a.versao and a.para):
            ap.error("informe a versão e --para, ou use --rollback")
        print(promover(cliente, a.modelo, a.versao, a.para, a.por, a.curadoria, a.motivo))


if __name__ == "__main__":
    main()
