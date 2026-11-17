"""Contratos do sistema multiagente (entrega 20/11; Semana 4 do manual).

Os agentes só conversam por `Mensagem`. O `Rastro` guarda todas, em ordem: é a prova da colaboração na demo
e o registro de auditoria de cada resposta. Nada de texto do documento do usuário vai para logs; o rastro
fica no resultado da tarefa, com as mesmas regras de guarda (RNF01).
"""
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .evidencias import Evidencias
from .explicacao import Explicacao
from .resposta import RespostaVerificada

NomeAgente = Literal["orquestrador", "triagem", "pesquisa", "analise", "comunicacao", "validacao"]
Acao = Literal["responder", "orientar_sem_aconselhar", "fora_escopo", "consulta_individual", "institucional",
               "outra_jurisdicao"]
Persona = Literal["leigo", "advogado"]


class Mensagem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ordem: int = Field(ge=0)
    de: NomeAgente
    para: NomeAgente
    tipo: Literal["pedido", "resultado", "devolucao", "aviso"]
    resumo: str = Field(description="uma linha legível: o que foi pedido ou entregue")
    dados: dict[str, Any] = Field(default_factory=dict)
    motivo: str | None = None
    ms: float | None = Field(default=None, description="tempo gasto pelo agente que respondeu")
    em: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DecisaoTriagem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    acao: Acao
    pergunta_sanitizada: str
    sinais: list[str] = Field(default_factory=list)
    motivo: str = ""
    resposta_fixa: str | None = Field(default=None, description="recusa com encaminhamento; não chama a LLM")

    @property
    def segue_para_busca(self) -> bool:
        return self.acao in ("responder", "orientar_sem_aconselhar")


class Rastro(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mensagens: list[Mensagem] = Field(default_factory=list)

    def registrar(self, de: NomeAgente, para: NomeAgente, tipo: str, resumo: str, **kw: Any) -> Mensagem:
        m = Mensagem(ordem=len(self.mensagens), de=de, para=para, tipo=tipo, resumo=resumo, **kw)
        self.mensagens.append(m)
        return m


class EstadoTarefa(BaseModel):
    """Estado explícito que o Orquestrador passa de agente em agente."""

    model_config = ConfigDict(extra="forbid")

    tarefa_id: str
    pergunta: str
    persona: Persona = "leigo"
    consulta: str | None = Field(default=None, description="consulta atual do Agente de Pesquisa")
    triagem: DecisaoTriagem | None = None
    evidencias: Evidencias | None = None
    explicacao: Explicacao | None = None
    resposta: RespostaVerificada | None = None
    frases_para_refazer: dict[int, str] = Field(default_factory=dict, description="ordem da frase -> motivo")
    novas_buscas: int = 0
    reescritas: int = 0
    rastro: Rastro = Field(default_factory=Rastro)
