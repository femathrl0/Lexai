"""Executa o worker: `uv run --group worker python -m worker.main`.

Só o worker carrega modelos. Ao iniciar, carrega do MLflow as versões marcadas "em uso" (worker/modelos).
"""
import os

from redis import Redis
from rq import Queue, Worker

from .filas import ORDEM_PRIORIDADE


def filas(redis: Redis) -> list[Queue]:
    return [Queue(nome, connection=redis) for nome in ORDEM_PRIORIDADE]


def main() -> None:
    redis = Redis.from_url(os.getenv("REDIS_URL", "redis://127.0.0.1:16379/0"))
    # TODO (Eng. de ML): worker.modelos.registro.carregar_em_uso() e checar orçamento de memória.
    Worker(filas(redis), connection=redis).work(with_scheduler=False)


if __name__ == "__main__":
    main()
