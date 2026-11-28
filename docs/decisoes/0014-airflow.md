# 0014 — Airflow para agendar o pipeline de ML

Data: 27/11/2026 · Felipe (Eng. de ML e MLOps).

**Contexto.** O pipeline (`dvc.yaml`), o monitoramento de deriva, a fila de aprendizado ativo e a limpeza do armazenamento rodavam à mão ou num workflow do GitHub sobre dados de exemplo. No servidor, falta quem os agende, registre cada execução e tente de novo quando falham.

**Decisão.** Apache Airflow 3.1.3 em `airflow standalone` (LocalExecutor, metadados no Postgres do Lexai), com três DAGs em `orquestracao/dags/`. Cada tarefa chama um comando do projeto num venv separado. O DVC decide o que refazer e o MLflow guarda os resultados. Promover modelo continua sendo uma decisão humana.

**Alternativa descartada.** Agendar com cron e GitHub Actions: o Actions não alcança o log de previsões do servidor, e o cron não tem histórico, nova tentativa automática nem visão por tarefa. Prefect e Dagster também atenderiam, mas o grupo pediu Airflow, que é o padrão da disciplina.
