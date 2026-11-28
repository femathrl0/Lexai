"""Treino e avaliação semanais: o pipeline do dvc.yaml estágio a estágio, terminando no portão de regressão.

Cada estágio é uma tarefa (log, tempo e reexecução separados na UI). Só roda o que mudou (dvc.lock). Se o portão de
regressão reprovar, a DAG falha e nada é promovido; promoção continua manual (`treino/promover.py`, com a Curadoria).
"""
from __future__ import annotations

from datetime import datetime, timedelta

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

from orquestracao.etapas import BAIXAR_LOTE, ESTAGIOS_DVC, repro

with DAG(
    dag_id="lexai_treino_avaliacao",
    description="dvc repro estágio a estágio + portão de regressão (Eng. de ML)",
    schedule="0 4 * * 1",  # segunda, 1h em Brasília
    start_date=datetime(2026, 11, 23),
    catchup=False,
    max_active_runs=1,  # o DVC trava o repositório: uma rodada por vez
    default_args={"retries": 1, "retry_delay": timedelta(minutes=10), "execution_timeout": timedelta(hours=3)},
    tags=["lexai", "ml", "dvc"],
) as dag:
    anterior = BashOperator(task_id="baixar_lote", bash_command=BAIXAR_LOTE)
    for estagio in ESTAGIOS_DVC:
        tarefa = BashOperator(task_id=estagio, bash_command=repro(estagio))
        anterior >> tarefa
        anterior = tarefa
