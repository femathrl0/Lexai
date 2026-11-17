"""Eventos que o worker publica no pub/sub e o backend repassa por SSE (manual: "Como a resposta volta")."""
from typing import Annotated, Literal

from pydantic import Field, TypeAdapter

from .base import Contrato, Versoes


class Status(Contrato):
    tipo: Literal["status"] = "status"
    etapa: Literal["na_fila", "lendo", "classificando", "buscando", "escrevendo", "verificando"]
    posicao_fila: int | None = None


class Frase(Contrato):
    tipo: Literal["frase"] = "frase"
    ordem: int = Field(ge=0)
    texto: str
    trecho_id: str
    trecho_texto: str
    fonte: str


class Aviso(Contrato):
    tipo: Literal["aviso"] = "aviso"
    categoria: Literal["incerteza", "sem_fonte", "recusa", "nova_foto"]
    texto: str


class Concluido(Contrato):
    tipo: Literal["concluido"] = "concluido"
    versoes: Versoes


class Erro(Contrato):
    tipo: Literal["erro"] = "erro"
    mensagem: str
    o_que_fazer: str


Evento = Annotated[Status | Frase | Aviso | Concluido | Erro, Field(discriminator="tipo")]
EVENTO = TypeAdapter(Evento)
