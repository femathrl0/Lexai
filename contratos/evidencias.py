from datetime import date
from typing import Literal

from pydantic import Field

from .base import Contrato

TipoFonte = Literal["lei", "sumula", "oj", "ementa", "documento_usuario"]


class TrechoEvidencia(Contrato):
    id: str
    indice: Literal["corpus_juridico", "trechos_usuario"]
    tipo_fonte: TipoFonte
    texto: str
    fonte: str = Field(description="ex.: CLT art. 477; Súmula 437 do TST")
    versao: str
    vigencia_inicio: date | None = None
    vigencia_fim: date | None = None
    nota_reranker: float


class Evidencias(Contrato):
    """Produz: Recuperador + Reranker. Consome: Explicador."""

    tarefa_id: str
    consulta: str
    trechos: list[TrechoEvidencia]
    sem_fonte_segura: bool = Field(default=False, description="nenhum trecho acima do limiar do reranker")
