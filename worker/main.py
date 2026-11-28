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


def bater(redis: Redis) -> None:
    """Batimento para o healthcheck do contêiner (worker/saude.py)."""
    import threading

    from .saude import INTERVALO, VALIDADE, chave

    def laco():
        while True:
            try:
                redis.set(chave(), "1", ex=VALIDADE)
            except Exception:  # noqa: BLE001 - Redis fora: o healthcheck vai acusar
                log.warning("sem batimento: Redis não respondeu")
            threading.Event().wait(INTERVALO)

    threading.Thread(target=laco, daemon=True, name="batimento").start()


def main() -> None:
    # socket_timeout=None: o redis-py 8 usa 5 s por padrão e corta a espera bloqueante da fila do RQ (BLPOP),
    # deixando o worker em "Timeout reading" sem nunca pegar tarefa; health_check_interval mantém a conexão viva.
    redis = Redis.from_url(os.getenv("REDIS_URL", "redis://127.0.0.1:16379/0"), socket_timeout=None,
                           health_check_interval=30)
    configurar("worker")
    for nome, m in em_uso().items():  # resolve uma vez; os pesos carregam na primeira tarefa
        log.info("modelo em uso", extra={"modelo": nome, "versao": m.rotulo, "origem_versao": m.origem})
    bater(redis)
    Worker(filas(redis), connection=redis).work(with_scheduler=False)


if __name__ == "__main__":
    main()
