"""Orquestrador: estado explícito, roteamento entre agentes e rastro de todas as mensagens.

Fluxo: Triagem → Pesquisa → Análise → Comunicação → Validação → resposta, com dois laços pedidos pela Validação:
"refazer frases" (volta à Análise, 1×) e "nova busca" (volta à Pesquisa, 1×). O verificador é o último portão:
nenhuma frase chega ao usuário sem passar por ele.
"""
from __future__ import annotations

import time
import uuid
from collections.abc import Callable

from contratos import Aviso, Concluido, Frase, RespostaVerificada, Status, Versoes
from contratos.agentes import EstadoTarefa
from contratos.eventos import Evento
from worker.evidencia import guardas

from .base import Agente, Saida

MAX_PASSOS = 12
ETAPA = {"pesquisa": "buscando", "analise": "escrevendo", "comunicacao": "escrevendo", "validacao": "verificando"}


def categoria_aviso(texto: str) -> str:
    if "removidas" in texto:
        return "incerteza"
    if "fonte jurídica segura" in texto:
        return "sem_fonte"
    return "encaminhamento"


class Orquestrador:
    nome = "orquestrador"
    responsabilidade = ("Coordena a tarefa: mantém o estado, chama o agente seguinte, aplica os limites de "
                        "retentativa (1 reescrita, 1 nova busca) e registra o rastro.")

    def __init__(self, triagem: Agente, pesquisa: Agente, analise: Agente, comunicacao: Agente, validacao: Agente,
                 publicar: Callable[[Evento], None] | None = None, ao_mensagem: Callable | None = None):
        self.agentes = {a.nome: a for a in (triagem, pesquisa, analise, comunicacao, validacao)}
        self.publicar = publicar or (lambda e: None)
        self.ao_mensagem = ao_mensagem or (lambda m: None)

    def _chamar(self, estado: EstadoTarefa, nome: str, pedido: str) -> Saida:
        r = estado.rastro
        self.ao_mensagem(r.registrar("orquestrador", nome, "pedido", pedido))
        if nome in ETAPA:
            self.publicar(Status(etapa=ETAPA[nome]))
        t0 = time.perf_counter()
        saida = self.agentes[nome].executar(estado)
        ms = round((time.perf_counter() - t0) * 1000, 1)
        if saida.tipo == "devolucao":
            m = r.registrar(nome, saida.devolver_para, "devolucao", saida.resumo, dados=saida.dados, ms=ms,
                            motivo="; ".join(f"frase {k}: {v}" for k, v in estado.frases_para_refazer.items()) or None)
        else:
            m = r.registrar(nome, "orquestrador", saida.tipo, saida.resumo, dados=saida.dados, ms=ms)
        self.ao_mensagem(m)
        return saida

    def responder(self, pergunta: str, persona: str = "leigo", tarefa_id: str | None = None) -> EstadoTarefa:
        estado = EstadoTarefa(tarefa_id=tarefa_id or uuid.uuid4().hex[:12], pergunta=pergunta, persona=persona)
        self._chamar(estado, "triagem", "classificar a intenção da pergunta")
        if not estado.triagem.segue_para_busca:
            estado.resposta = RespostaVerificada(tarefa_id=estado.tarefa_id, frases=[], versoes=Versoes(),
                                                 avisos=[estado.triagem.resposta_fixa, guardas.AVISO_LEGAL])
            self.publicar(Aviso(categoria="recusa", texto=estado.triagem.resposta_fixa))
            self.publicar(Concluido(versoes=estado.resposta.versoes))
            return estado

        proximo, passos = "pesquisa", 0
        pedidos = {"pesquisa": "buscar trechos de lei e jurisprudência para a consulta",
                   "analise": "explicar a pergunta frase a frase, cada frase com o trecho que a sustenta",
                   "comunicacao": f"adaptar a explicação ao público '{persona}' sem mudar o conteúdo",
                   "validacao": "conferir cada frase contra o trecho citado e liberar só o que for sustentado"}
        while proximo and passos < MAX_PASSOS:
            passos += 1
            saida = self._chamar(estado, proximo, pedidos[proximo])
            if proximo == "validacao":
                proximo = saida.devolver_para  # None = resposta liberada
                if proximo == "analise":
                    pedidos["analise"] = "reescrever as frases reprovadas usando o motivo da Validação"
                elif proximo == "pesquisa":
                    pedidos["pesquisa"] = "nova busca com consulta reformulada (nenhuma frase teve fonte)"
            else:
                proximo = {"pesquisa": "analise", "analise": "comunicacao", "comunicacao": "validacao"}[proximo]

        por_id = {t.id: t for t in estado.evidencias.trechos}
        for f in estado.resposta.frases:
            self.publicar(Frase(ordem=f.ordem, texto=f.texto, trecho_id=f.trecho_id, fonte=f.fonte,
                                trecho_texto=por_id[f.trecho_id].texto[:600]))
        for a in estado.resposta.avisos:
            self.publicar(Aviso(categoria=categoria_aviso(a), texto=a))
        self.publicar(Concluido(versoes=estado.resposta.versoes))
        return estado
