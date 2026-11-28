"""Executa o worker: `uv run --group worker python -m worker.main`.

Só o worker carrega modelos. Ao iniciar, carrega do MLflow as versões marcadas "em uso" (worker/modelos).
"""
import os

from redis import Redis
from rq import Queue, Worker

from comum.log import configurar, registrador

from .filas import ORDEM_PRIORIDADE
from .modelos.registro import em_uso

log = registrador("worker")


def filas(redis: Redis) -> list[Queue]:
    return [Queue(nome, connection=redis) for nome in ORDEM_PRIORIDADE]


def main() -> None:
    redis = Redis.from_url(os.getenv("REDIS_URL", "redis://127.0.0.1:16379/0"))
    configurar("worker")
    for nome, m in em_uso().items():  # resolve uma vez; os pesos carregam na primeira tarefa
        log.info("modelo em uso", extra={"modelo": nome, "versao": m.rotulo, "origem_versao": m.origem})
    Worker(filas(redis), connection=redis).work(with_scheduler=False)


if __name__ == "__main__":
    main()
