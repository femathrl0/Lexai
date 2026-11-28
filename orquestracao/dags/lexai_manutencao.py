"""Manutenção diária do armazenamento (RNF01): apaga entradas de upload esquecidas e originais com o prazo de guarda
vencido (`PRAZO_GUARDA_DIAS`). Ver worker/manutencao.py."""
from __future__ import annotations

from datetime import datetime, timedelta

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

from orquestracao.etapas import LIMPAR_ARMAZENAMENTO

with DAG(
    dag_id="lexai_manutencao",
    description="limpeza da entrada e do prazo de guarda no S3",
    schedule="30 6 * * *",
    start_date=datetime(2026, 11, 23),
    catchup=False,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=5)},
    tags=["lexai", "privacidade"],
) as dag:
    BashOperator(task_id="limpar_armazenamento", bash_command=LIMPAR_ARMAZENAMENTO)
