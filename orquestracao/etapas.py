"""O que cada DAG roda — sem importar o Airflow, para o CI do projeto conferir sem instalá-lo.

As tarefas chamam comandos do projeto num ambiente Python separado do Airflow (`LEXAI_PYTHON`, padrão
/opt/lexai-venv/bin), na raiz do repositório (`LEXAI_RAIZ`, padrão /opt/lexai/app). Assim as dependências do
Airflow e as do projeto (torch, mlflow, evidently…) não precisam caber no mesmo ambiente.
"""
from __future__ import annotations

import os

RAIZ = os.getenv("LEXAI_RAIZ", "/opt/lexai/app")
BIN = os.getenv("LEXAI_PYTHON", "/opt/lexai-venv/bin")

# Estágios do dvc.yaml na ordem do treino semanal. `dvc repro -s` só refaz o estágio se código, dados ou parâmetros
# mudaram desde o dvc.lock — rodar a DAG sem mudança nenhuma não treina nada.
ESTAGIOS_DVC = (
    "esquemas",
    "teste_congelado",
    "classificador_tipo",
    "segmentador",
    "resultado_pedido",
    "extrator_campos",
    "intencao",
    "ruido_ocr",
    "referencia_deriva",
    "portao_regressao",
    "final",
)


def comando(*args: str) -> str:
    """Linha de shell que roda um módulo do projeto no ambiente do projeto."""
    return f"cd {RAIZ} && {BIN}/python -m {' '.join(args)}"


def repro(estagio: str) -> str:
    return f"cd {RAIZ} && {BIN}/dvc repro --single-item {estagio}"


BAIXAR_LOTE = comando("treino.classificador_tipo", "baixar")
DERIVA = comando("treino.deriva", "relatorio") + "; codigo=$?; [ $codigo -eq 0 ] || [ $codigo -eq 2 ]"  # 2 = alerta
APRENDIZADO_ATIVO = comando("treino.aprendizado_ativo")
LIMPAR_ARMAZENAMENTO = comando("worker.manutencao")
RELATORIO_DERIVA = f"{RAIZ}/dados/output/monitoramento/deriva.json"
