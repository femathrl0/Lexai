"""Enfileiramento. O backend nunca processa documento: cria a tarefa e a põe na fila certa."""
import uuid

from redis import Redis
from rq import Queue, Retry

from worker.filas import DOCUMENTOS, MAX_TENTATIVAS, PERGUNTAS

# Caminho das funções no worker, passado como string para o backend não importar o pipeline.
FUNCAO_DOCUMENTO = "worker.pipelines.processar_documento"
FUNCAO_PERGUNTA = "worker.pipelines.responder_pergunta"


def enfileirar(redis: Redis, fila: str, funcao: str, **kwargs) -> str:
    tarefa_id = uuid.uuid4().hex
    # job_id = tarefa_id torna a reentrega idempotente; no máximo duas tentativas (manual).
    Queue(fila, connection=redis).enqueue(
        funcao, tarefa_id=tarefa_id, job_id=tarefa_id, retry=Retry(max=MAX_TENTATIVAS - 1), **kwargs
    )
    return tarefa_id


def enfileirar_documento(redis: Redis, usuario_id: str, caminho_temp: str, guardar: bool) -> str:
    return enfileirar(redis, DOCUMENTOS, FUNCAO_DOCUMENTO, usuario_id=usuario_id, caminho=caminho_temp, guardar=guardar)


def enfileirar_pergunta(redis: Redis, usuario_id: str, pergunta: str, documento_id: str | None) -> str:
    return enfileirar(redis, PERGUNTAS, FUNCAO_PERGUNTA, usuario_id=usuario_id, pergunta=pergunta,
                      documento_id=documento_id)
