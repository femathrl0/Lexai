from typing import Literal

from pydantic import Field

from .base import Contrato, Versoes


class FraseAprovada(Contrato):
    ordem: int = Field(ge=0)
    texto: str
    trecho_id: str
    fonte: str
    veredito: Literal["sustenta"] = "sustenta"


class RespostaVerificada(Contrato):
    """Produz: Verificador + Guarda de saída. Consome: Backend, app."""

    tarefa_id: str
    frases: list[FraseAprovada]
    avisos: list[str] = Field(default_factory=list)
    versoes: Versoes
