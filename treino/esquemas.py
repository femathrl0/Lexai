"""Esquemas dos dados de treino e avaliação (Pandera) — manual: "validação de esquema que para o pipeline".

    uv run --group treino python -m treino.esquemas        # valida tudo e grava treino/relatorios/esquemas.json

Cada conjunto tem um esquema; `validar(nome, df)` levanta `SchemaErrors` com todas as violações. O lote RepoJus é
validado ao carregar (`classificador_tipo.carregar_lote`), então um lote fora do esquema para o pipeline antes do
treino. Regras de privacidade entram no esquema: o log de previsões não pode ter colunas com conteúdo do usuário.
"""
from __future__ import annotations

import json
import sys

from treino.comum import RAIZ, RELATORIOS, salvar_json

CNJ = r"^\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}$"
ROTULOS_NLI = ["sustenta", "contradiz", "nao_trata"]
PROIBIDAS = {"texto", "pergunta", "frase", "trecho", "nome", "cpf", "usuario_id", "email"}
ACOES = ["responder", "orientar_sem_aconselhar", "fora_escopo", "consulta_individual", "institucional", "outra_jurisdicao"]


def esquemas() -> dict:
    import pandera.pandas as pa

    nao_vazio = pa.Check.str_length(min_value=1)
    return {
        "repojus": pa.DataFrameSchema({
            "doc_id": pa.Column(str, unique=True),
            "processo": pa.Column(str, pa.Check.str_matches(CNJ)),
            "tipo": pa.Column(str, nao_vazio),
            "texto_integral": pa.Column(str, pa.Check.str_length(min_value=200)),
        }, checks=pa.Check(lambda df: len(df) >= 1000, error="lote pequeno demais"), strict=False),
        "pares_ouro_verificador": pa.DataFrameSchema({
            "id": pa.Column(str, unique=True), "frase": pa.Column(str, nao_vazio), "trecho": pa.Column(str, nao_vazio),
            "fonte": pa.Column(str, nao_vazio), "rotulo": pa.Column(str, pa.Check.isin(ROTULOS_NLI)),
            "status": pa.Column(str, nao_vazio),
        }, checks=pa.Check(lambda df: df.rotulo.nunique() == 3, error="faltam rótulos"), strict=False),
        "perguntas_demo": pa.DataFrameSchema({
            "id": pa.Column(str, unique=True), "pergunta": pa.Column(str, nao_vazio),
            "acao_esperada": pa.Column(str, pa.Check.isin(ACOES)),
        }, strict=False),
        "intencao": pa.DataFrameSchema({
            "id": pa.Column(str, unique=True), "pergunta": pa.Column(str, nao_vazio, unique=True),
            "acao_esperada": pa.Column(str, pa.Check.isin(ACOES)), "molde": pa.Column(str, nao_vazio),
        }, strict=True),
        "previsoes": pa.DataFrameSchema({
            "modelo": pa.Column(str, nao_vazio), "versao": pa.Column(str), "tarefa": pa.Column(str, pa.Check.str_length(16, 16)),
            "confianca": pa.Column(float, pa.Check.in_range(0, 1), nullable=True), "abstencao": pa.Column(bool),
        }, checks=pa.Check(lambda df: not (PROIBIDAS & set(df.columns)),
                           error="coluna com conteúdo do usuário no log de previsões"), strict=False),
        "referencia_deriva": pa.DataFrameSchema({
            c: pa.Column(float, pa.Check.ge(0), coerce=True) for c in
            ("confianca_tipo", "abstencao_tipo", "caracteres", "pedidos", "fracao_pedidos_sem_resultado",
             "campos_preenchidos", "qualidade_leitura")}, strict=True),
    }


def validar(nome: str, df):
    return esquemas()[nome].validate(df, lazy=True)


def _jsonl(caminho):
    import pandas as pd

    return pd.DataFrame([json.loads(x) for x in caminho.read_text(encoding="utf-8").splitlines() if x.strip()])


def conjuntos() -> dict:
    """Arquivos versionados (+ o lote bruto, se existir) e o esquema de cada um."""
    import pandas as pd

    from treino.classificador_tipo import CAMINHOS_ALTERNATIVOS, LOTE

    out = {
        "pares_ouro_verificador": lambda: _jsonl(RAIZ / "avaliacao/pares_ouro/verificador_v1.jsonl"),
        "perguntas_demo": lambda: _jsonl(RAIZ / "avaliacao/agentes/perguntas_demo.jsonl"),
        "intencao": lambda: _jsonl(RAIZ / "avaliacao/dados/intencao/casos_v1.jsonl").drop(columns=["status"]),
        "previsoes": lambda: _jsonl(RAIZ / "avaliacao/monitoramento/previsoes_exemplo.jsonl"),
        "referencia_deriva": lambda: pd.read_csv(RAIZ / "avaliacao/monitoramento/referencia.csv"),
    }
    lote = next((c for c in (LOTE["caminho"], *CAMINHOS_ALTERNATIVOS) if c.exists()), None)
    if lote is not None:
        out["repojus"] = lambda: pd.read_parquet(lote, columns=["doc_id", "processo", "tipo", "texto_integral"])
    return out


def main() -> None:
    import pandera.errors as pe

    resultado, falhou = {}, False
    for nome, carregar in conjuntos().items():
        try:
            df = carregar()
            validar(nome, df)
            resultado[nome] = {"linhas": len(df), "ok": True}
        except pe.SchemaErrors as e:
            falhou = True
            resultado[nome] = {"ok": False, "erros": e.failure_cases.head(20).astype(str).to_dict("records")}
        print(f"{'ok' if resultado[nome]['ok'] else 'FALHOU':>6}  {nome}", flush=True)
    salvar_json(resultado, RELATORIOS / "esquemas.json")
    if falhou:
        sys.exit(1)


if __name__ == "__main__":
    main()
