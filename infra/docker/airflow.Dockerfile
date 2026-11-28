# Airflow (orquestração dos pipelines de ML). Imagem grande (~7 GB, torch CPU no venv do projeto): construída
# pelo workflow imagens.yml; localmente, só numa máquina com folga de disco.
# O Airflow fica no ambiente da imagem oficial; o projeto (treino +
# worker, com torch CPU) vai num venv separado em /opt/lexai-venv, chamado pelas tarefas (orquestracao/etapas.py).
FROM apache/airflow:3.1.3-python3.12
USER root
COPY --from=ghcr.io/astral-sh/uv:0.13.4 /uv /bin/uv
RUN mkdir -p /opt/lexai/app /opt/lexai-venv && chown -R airflow:0 /opt/lexai /opt/lexai-venv
USER airflow
ENV UV_PROJECT_ENVIRONMENT=/opt/lexai-venv UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 UV_PYTHON_DOWNLOADS=never UV_NO_CACHE=1 \
    LEXAI_RAIZ=/opt/lexai/app LEXAI_PYTHON=/opt/lexai-venv/bin PYTHONPATH=/opt/lexai/app \
    AIRFLOW__CORE__DAGS_FOLDER=/opt/lexai/app/orquestracao/dags AIRFLOW__CORE__LOAD_EXAMPLES=False
WORKDIR /opt/lexai/app
COPY --chown=airflow:0 pyproject.toml uv.lock ./
RUN uv sync --frozen --no-default-groups --group treino --group worker --no-install-project --python /usr/python/bin/python3.12
# Código do projeto na imagem (sem .git): o DVC roda sem SCM e o commit vem do build (rastreado no MLflow).
COPY --chown=airflow:0 . /opt/lexai/app
ARG LEXAI_GIT_COMMIT=desconhecido
ENV LEXAI_GIT_COMMIT=${LEXAI_GIT_COMMIT}
RUN /opt/lexai-venv/bin/dvc config --local core.no_scm true
COPY --chown=airflow:0 infra/docker/airflow_entrada.py /opt/airflow/airflow_entrada.py
ENTRYPOINT ["/usr/bin/dumb-init", "--", "python", "/opt/airflow/airflow_entrada.py"]
