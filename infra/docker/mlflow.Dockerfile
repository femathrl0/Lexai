# MLflow de equipe: metadados no Postgres (banco "mlflow") e artefatos no MinIO (bucket "mlflow").
FROM ghcr.io/mlflow/mlflow:v3.18.0
RUN pip install --no-cache-dir "psycopg2-binary>=2.9" "boto3>=1.34"
COPY infra/docker/mlflow_entrada.py /mlflow_entrada.py
ENTRYPOINT ["python", "/mlflow_entrada.py"]
