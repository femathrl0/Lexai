"""API do Lexai (FastAPI). Esqueleto da semana 1: saúde, envio, pergunta e streaming SSE.

TODO (issues do Eng. de software): autenticação OAuth2 + Argon2, permissões por tarefa, registro de consentimento,
reconexão do SSE a partir da última frase gravada no banco, "apagar meus dados".
"""
import asyncio
import tempfile
from collections.abc import AsyncIterator

from fastapi import Depends, FastAPI, Form, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from redis import Redis
from redis.asyncio import Redis as AsyncRedis

from worker.filas import canal_tarefa

from . import filas
from .config import config

app = FastAPI(title="Lexai", version="0.1.0")

AVISO_FIXO = (
    "O Lexai explica o que o documento diz; não substitui advogado, Defensoria Pública ou o setor de atermação."
)


def get_redis() -> Redis:
    return Redis.from_url(config.redis_url)


def usuario_atual() -> str:
    # TODO: substituir pela sessão autenticada (OAuth2 senha + Argon2, sessões que expiram).
    return "anonimo"


class Pergunta(BaseModel):
    pergunta: str
    documento_id: str | None = None


class TarefaCriada(BaseModel):
    tarefa_id: str
    aviso: str = AVISO_FIXO


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/tarefas/documentos", response_model=TarefaCriada)
async def enviar_documento(
    arquivo: UploadFile,
    guardar: bool = Form(False),
    redis: Redis = Depends(get_redis),
    usuario: str = Depends(usuario_atual),
) -> TarefaCriada:
    # Sem opt-in o arquivo vive só em pasta temporária e é descartado pelo worker (RNF01).
    with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{arquivo.filename}") as tmp:
        tmp.write(await arquivo.read())
    return TarefaCriada(tarefa_id=filas.enfileirar_documento(redis, usuario, tmp.name, guardar))


@app.post("/tarefas/perguntas", response_model=TarefaCriada)
def enviar_pergunta(
    corpo: Pergunta, redis: Redis = Depends(get_redis), usuario: str = Depends(usuario_atual)
) -> TarefaCriada:
    return TarefaCriada(tarefa_id=filas.enfileirar_pergunta(redis, usuario, corpo.pergunta, corpo.documento_id))


@app.get("/tarefas/{tarefa_id}/eventos")
async def eventos(tarefa_id: str, request: Request) -> StreamingResponse:
    """Repassa o pub/sub da tarefa como SSE. TODO: checar dono da tarefa e reenviar do banco o que faltou."""

    async def fluxo() -> AsyncIterator[str]:
        redis = AsyncRedis.from_url(config.redis_url)
        pubsub = redis.pubsub()
        await pubsub.subscribe(canal_tarefa(tarefa_id))
        try:
            while not await request.is_disconnected():
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg is None:
                    await asyncio.sleep(0.05)
                    continue
                dado = msg["data"].decode()
                yield f"data: {dado}\n\n"
                if '"tipo":"concluido"' in dado or '"tipo":"erro"' in dado:
                    break
        finally:
            await pubsub.unsubscribe()
            await redis.aclose()

    return StreamingResponse(fluxo(), media_type="text/event-stream")
