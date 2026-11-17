from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from contratos.agentes import EstadoTarefa, NomeAgente


@dataclass
class Saida:
    """O que um agente devolve ao Orquestrador: uma linha legível e os dados que vão para o rastro."""

    resumo: str
    dados: dict[str, Any] = field(default_factory=dict)
    tipo: str = "resultado"  # resultado | aviso | devolucao
    devolver_para: str | None = None  # só na devolução: agente que deve refazer o trabalho


class Agente(ABC):
    nome: NomeAgente
    responsabilidade: str

    @abstractmethod
    def executar(self, estado: EstadoTarefa) -> Saida:
        """Lê o estado, escreve só os campos pelos quais responde e devolve um resumo para o rastro."""
