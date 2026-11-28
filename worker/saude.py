"""Healthcheck do contêiner do worker: `python -m worker.saude` sai 0 se o Redis responde e o batimento deste worker
(gravado por worker.main a cada 30 s) tem menos de 90 s."""
from __future__ import annotations

import os
import socket
import sys

CHAVE = "lexai:worker:batimento:{host}"
INTERVALO = 30
VALIDADE = 90


def chave() -> str:
    return CHAVE.format(host=socket.gethostname())


def main() -> int:
    from redis import Redis

    try:
        r = Redis.from_url(os.getenv("REDIS_URL", "redis://127.0.0.1:16379/0"), socket_timeout=3)
        return 0 if r.exists(chave()) else 1
    except Exception:  # noqa: BLE001
        return 1


if __name__ == "__main__":
    sys.exit(main())
