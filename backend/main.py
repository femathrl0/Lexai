"""API do Lexai (FastAPI). Esqueleto da semana 1: saúde, envio, pergunta e streaming SSE.

TODO (issues do Eng. de software): autenticação OAuth2 + Argon2, permissões por tarefa, registro de consentimento,
reconexão do SSE a partir da última frase gravada no banco, "apagar meus dados".
"""
import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from redis import Redis
from redis.asyncio import Redis as AsyncRedis

from comum.log import configurar, registrador
from worker.filas import canal_tarefa

from . import filas
from .armazenamento import ArquivoRecusado, guardar_entrada
from .config import config

log = registrador("backend")


@asynccontextmanager
async def ciclo(_app: FastAPI):
    configurar("backend")
    log.info("backend no ar", extra={"ambiente": config.lexai_ambiente, "minio": bool(config.minio_endpoint)})
    yield


app = FastAPI(title="Lexai", version="0.1.0", lifespan=ciclo)
if config.cors_origens:
    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in config.cors_origens.split(",")],
                       allow_methods=["GET", "POST"], allow_headers=["*"])

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
    """Liveness: o processo responde (o orquestrador de contêineres reinicia se falhar)."""
    return {"status": "ok"}


@app.get("/ready")
def ready(redis: Redis = Depends(get_redis)) -> JSONResponse:
    """Readiness: Redis (fila) e Postgres respondem e há worker vivo. 503 tira o backend do balanceamento."""
    checagens: dict[str, str] = {}
    try:
        redis.ping()
        checagens["redis"] = "ok"
        from rq import Worker

        checagens["workers"] = str(len(Worker.all(connection=redis)))
    except Exception as e:  # noqa: BLE001
        checagens["redis"] = f"falha: {type(e).__name__}"
    if config.database_url:
        try:
            from sqlalchemy import create_engine, text

            with create_engine(config.database_url, pool_pre_ping=True).connect() as c:
                c.execute(text("select 1"))
            checagens["postgres"] = "ok"
        except Exception as e:  # noqa: BLE001
            checagens["postgres"] = f"falha: {type(e).__name__}"
    pronto = all(v == "ok" for k, v in checagens.items() if k != "workers")
    return JSONResponse({"status": "pronto" if pronto else "indisponivel", **checagens}, status_code=200 if pronto else 503)


@app.post("/tarefas/documentos", response_model=TarefaCriada)
async def enviar_documento(
    arquivo: UploadFile,
    guardar: bool = Form(False),
    redis: Redis = Depends(get_redis),
    usuario: str = Depends(usuario_atual),
) -> TarefaCriada:
    # Sem opt-in a cópia de entrada é apagada pelo worker depois da análise (RNF01).
    dados = await arquivo.read(config.upload_max_mb * 2**20 + 1)
    try:
        referencia = guardar_entrada(dados)
    except ArquivoRecusado as e:
        raise HTTPException(status_code=413 if "maior" in str(e) else 415, detail=str(e)) from e
    return TarefaCriada(tarefa_id=filas.enfileirar_documento(redis, usuario, referencia, guardar))


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
