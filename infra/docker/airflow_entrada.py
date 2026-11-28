"""Entrada do contêiner do Airflow: cria o banco "airflow" no Postgres do Lexai se faltar e sobe o `airflow standalone`
(api-server, scheduler, dag-processor e triggerer num processo, LocalExecutor) — o tamanho certo para um servidor só."""
import os
import time

import psycopg2

pg = dict(host=os.environ.get("POSTGRES_HOST", "postgres"), user=os.environ["POSTGRES_USER"],
          password=os.environ["POSTGRES_PASSWORD"], dbname=os.environ.get("POSTGRES_DB", "lexai"))
for _ in range(30):
    try:
        conn = psycopg2.connect(**pg)
        break
    except psycopg2.OperationalError:
        time.sleep(2)
else:
    raise SystemExit("Postgres não respondeu")
conn.autocommit = True
with conn.cursor() as c:
    c.execute("select 1 from pg_database where datname = 'airflow'")
    if not c.fetchone():
        c.execute("create database airflow")
conn.close()
os.environ.setdefault("AIRFLOW__DATABASE__SQL_ALCHEMY_CONN",
                      f"postgresql+psycopg2://{pg['user']}:{pg['password']}@{pg['host']}:5432/airflow")
os.environ.setdefault("AIRFLOW__CORE__EXECUTOR", "LocalExecutor")
os.execvp("airflow", ["airflow", "standalone"])
