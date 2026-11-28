"""Carrega as DAGs com o Airflow e falha se houver erro de importação (CI: job "DAGs do Airflow").

    docker run --rm -v "$PWD:/opt/lexai/app" -w /opt/lexai/app -e PYTHONPATH=/opt/lexai/app \\
      apache/airflow:3.1.3-python3.12 python -m orquestracao.checar_dags
"""
import sys
from pathlib import Path

from airflow.models.dagbag import DagBag

pasta = Path(__file__).with_name("dags")
bag = DagBag(dag_folder=str(pasta), include_examples=False)
for arquivo, erro in bag.import_errors.items():
    print(f"ERRO {arquivo}:\n{erro}", file=sys.stderr)
for dag_id, dag in sorted(bag.dags.items()):
    print(f"{dag_id}: {len(dag.tasks)} tarefas, agenda {dag.timetable.summary}")
    for t in dag.tasks:
        print(f"   {t.task_id} ← {sorted(t.upstream_task_ids)}")
sys.exit(1 if bag.import_errors or len(bag.dags) != 3 else 0)
