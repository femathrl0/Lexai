from typing import Literal

from pydantic import Field

from .base import Contrato

Resultado = Literal["procedente", "improcedente", "parcialmente_procedente", "nao_identificado"]


class Campo(Contrato):
    nome: str = Field(description="ex.: reclamante, reclamada, data_audiencia, valor_causa")
    valor: str | None = Field(description="None = 'não identificado'; nunca adivinhado")
    confianca: float = Field(ge=0, le=1)
    trecho_id: str | None = None


class ResultadoPedido(Contrato):
    pedido: str
    resultado: Resultado
    confianca: float = Field(ge=0, le=1)
    trecho_id: str | None = None


class Classificacao(Contrato):
    """Produz: Classificador de ML. Consome: Recuperador, Explicador, app."""

    tarefa_id: str
    tipo_documento: str | None
    confianca_tipo: float = Field(ge=0, le=1)
    fase: str | None
    confianca_fase: float = Field(ge=0, le=1)
    campos: list[Campo] = Field(default_factory=list)
    pedidos: list[ResultadoPedido] = Field(default_factory=list)
    abstencao: bool = Field(default=False, description="confiança abaixo do limiar calibrado (RNF04)")
