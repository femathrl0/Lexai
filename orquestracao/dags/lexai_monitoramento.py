"""Monitoramento diário: deriva (Evidently) sobre o log de previsões do worker; com alerta, gera o lote de anotação.

O log de previsões chega pelo volume compartilhado com o worker (`dados/output/previsoes`). Sem alerta, a DAG termina
depois do relatório; com alerta (metade das colunas com deriva ou abstenção +10 pontos), roda o aprendizado ativo.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG, task

from orquestracao.etapas import APRENDIZADO_ATIVO, DERIVA, RELATORIO_DERIVA

with DAG(
    dag_id="lexai_monitoramento",
    description="deriva + fila de aprendizado ativo (Eng. de ML)",
    schedule="0 9 * * *",  # 6h em Brasília
    start_date=datetime(2026, 11, 23),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 1, "retry_delay": timedelta(minutes=5)},
    tags=["lexai", "monitoramento"],
) as dag:
    deriva = BashOperator(task_id="relatorio_deriva", bash_command=DERIVA)

    @task.short_circuit(task_id="houve_alerta")
    def houve_alerta() -> bool:
        arq = Path(RELATORIO_DERIVA)
        if not arq.exists():
            return False
        alertas = json.loads(arq.read_text(encoding="utf-8")).get("alertas", [])
        print("alertas:", alertas)
        return bool(alertas)

    lote = BashOperator(task_id="lote_aprendizado_ativo", bash_command=APRENDIZADO_ATIVO)
    deriva >> houve_alerta() >> lote
