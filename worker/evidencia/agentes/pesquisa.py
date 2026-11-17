from __future__ import annotations

from pydantic import BaseModel, Field

from contratos import Evidencias
from contratos.agentes import EstadoTarefa

from .base import Agente, Saida
from .buscadores import Buscador
from .llm import LLM


class ConsultaReformulada(BaseModel):
    consulta: str = Field(description="consulta curta em termos jurídicos trabalhistas, sem dados pessoais")


class AgentePesquisa(Agente):
    nome = "pesquisa"
    responsabilidade = ("Research Agent: busca híbrida (palavra-chave + vetor, RRF) e reranker no corpus jurídico, "
                        "com cota por tipo de fonte; descarta trechos abaixo do limiar e sinaliza falta de fonte segura; "
                        "reformula a consulta quando a Validação pede nova busca.")

    def __init__(self, buscador: Buscador, llm: LLM | None = None, limiar: float | None = None, por_fonte: int = 3):
        self.buscador, self.llm, self.limiar, self.por_fonte = buscador, llm, limiar, por_fonte

    def _reformular(self, estado: EstadoTarefa) -> str:
        if self.llm is None:
            return f"{estado.consulta} CLT direito do trabalho"
        r = self.llm.gerar(
            "Você reescreve perguntas de trabalhadores como consultas de busca em legislação trabalhista brasileira. "
            "Use os termos técnicos (ex.: verbas rescisórias, aviso prévio, art. 477 da CLT). Responda só a consulta.",
            f"Pergunta: {estado.triagem.pergunta_sanitizada}\nConsulta anterior, que não achou fonte suficiente: "
            f"{estado.consulta}", ConsultaReformulada)
        return r.consulta

    def executar(self, estado: EstadoTarefa) -> Saida:
        reformulou = estado.evidencias is not None  # segunda passada = pedido da Validação
        if reformulou:
            estado.consulta = self._reformular(estado)
        trechos = self.buscador.buscar(estado.consulta, por_fonte=self.por_fonte)
        if self.limiar is not None:
            trechos = [t for t in trechos if t.nota_reranker >= self.limiar]
        estado.evidencias = Evidencias(tarefa_id=estado.tarefa_id, consulta=estado.consulta, trechos=trechos,
                                       sem_fonte_segura=not trechos)
        tipos = {}
        for t in trechos:
            tipos[t.tipo_fonte] = tipos.get(t.tipo_fonte, 0) + 1
        resumo = (f"{'consulta reformulada: ' + repr(estado.consulta) + '; ' if reformulou else ''}"
                  f"{len(trechos)} trechos ({', '.join(f'{v} {k}' for k, v in tipos.items()) or 'nenhum'})"
                  f"{' — SEM FONTE SEGURA' if not trechos else ''}")
        return Saida(resumo, dict(consulta=estado.consulta, buscador=self.buscador.versao,
                                  trechos=[dict(id=t.id, fonte=t.fonte, nota=t.nota_reranker) for t in trechos]),
                     tipo="aviso" if not trechos else "resultado")
