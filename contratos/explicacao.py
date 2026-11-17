from pydantic import Field

from .base import Contrato


class FraseGerada(Contrato):
    ordem: int = Field(ge=0)
    texto: str
    trecho_id: str | None = Field(description="id do trecho que sustenta a frase (RNF03)")


class Explicacao(Contrato):
    """Produz: Explicador (LLM). Consome: Verificador."""

    tarefa_id: str
    prompt_id: str
    modelo_llm: str
    frases: list[FraseGerada]
