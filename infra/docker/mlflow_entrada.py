"""Entrada do contêiner do MLflow: cria o banco e o bucket se faltarem e sobe o servidor."""
import os
import sys
import time

import boto3
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
    sys.exit("Postgres não respondeu")
conn.autocommit = True
with conn.cursor() as c:
    c.execute("select 1 from pg_database where datname = 'mlflow'")
    if not c.fetchone():
        c.execute("create database mlflow")
conn.close()

s3 = boto3.client("s3", endpoint_url=os.environ["MLFLOW_S3_ENDPOINT_URL"])
if "mlflow" not in [b["Name"] for b in s3.list_buckets().get("Buckets", [])]:
    s3.create_bucket(Bucket="mlflow")

uri = f"postgresql+psycopg2://{pg['user']}:{pg['password']}@{pg['host']}:5432/mlflow"
os.execvp("mlflow", ["mlflow", "server", "--host", "0.0.0.0", "--port", "5000", "--backend-store-uri", uri,
                     "--artifacts-destination", "s3://mlflow", "--serve-artifacts",
                     "--allowed-hosts", os.environ.get("MLFLOW_HOSTS", "localhost:*,127.0.0.1:*,mlflow:*")])
