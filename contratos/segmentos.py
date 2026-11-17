from typing import Literal

from .base import Contrato, Posicao

Parte = Literal["relatorio", "fundamentacao", "dispositivo", "outro"]


class Trecho(Contrato):
    id: str
    parte: Parte
    texto: str
    posicoes: list[Posicao]


class Segmentos(Contrato):
    """Produz: Segmentador. Consome: Classificador, Indexação."""

    tarefa_id: str
    metodo: Literal["regras", "modelo"]
    trechos: list[Trecho]
