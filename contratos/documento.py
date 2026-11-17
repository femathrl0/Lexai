from typing import Literal

from pydantic import Field

from .base import Contrato, Posicao


class Bloco(Contrato):
    id: str
    texto: str
    posicao: Posicao


class Pagina(Contrato):
    numero: int = Field(ge=1)
    blocos: list[Bloco]


class DocumentoLido(Contrato):
    """Produz: Leitor (Eng. de dados). Consome: Segmentador."""

    tarefa_id: str
    origem: Literal["nativo", "ocr"]
    qualidade_leitura: float = Field(ge=0, le=1, description="permite ao app dizer 'não consegui ler bem'")
    motivo_baixa_qualidade: str | None = None
    paginas: list[Pagina]
