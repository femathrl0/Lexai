"""Função de publicação fornecida pelo Eng. de software e usada pelo Eng. de IA.

Cada evento é gravado em `resultados` (fonte da verdade) e publicado no canal da tarefa (entrega rápida).
"""
from collections.abc import Callable

from redis import Redis

from contratos.eventos import EVENTO, Evento

from .filas import canal_tarefa

Gravador = Callable[[str, Evento], None]


def _sem_banco(tarefa_id: str, evento: Evento) -> None:  # pragma: no cover - substituído quando o banco existir
    """TODO (Eng. de software): gravar em resultados com número de ordem antes de publicar."""


def publicar(redis: Redis, tarefa_id: str, evento: Evento, gravar: Gravador = _sem_banco) -> None:
    gravar(tarefa_id, evento)
    redis.publish(canal_tarefa(tarefa_id), EVENTO.dump_json(evento).decode())
