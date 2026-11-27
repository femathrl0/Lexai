from __future__ import annotations

from contratos.agentes import DecisaoTriagem, EstadoTarefa
from worker.evidencia import guardas
from worker.evidencia.explicador import RESPOSTAS_FIXAS

from .base import Agente, Saida


class AgenteTriagem(Agente):
    nome = "triagem"
    responsabilidade = ("Guarda de entrada: classifica a intenção da pergunta, mascara dados pessoais e desvia "
                        "pedidos fora do escopo ou de consulta individual, com encaminhamento e sem chamar a LLM.")

    def executar(self, estado: EstadoTarefa) -> Saida:
        r = guardas.verificar_entrada(estado.pergunta)
        estado.triagem = DecisaoTriagem(acao=r.acao, pergunta_sanitizada=r.pergunta_sanitizada, sinais=r.sinais,
                                        motivo=r.motivo, resposta_fixa=RESPOSTAS_FIXAS.get(r.acao))
        estado.consulta = r.pergunta_sanitizada
        destino = "segue para a Pesquisa" if estado.triagem.segue_para_busca else "resposta fixa com encaminhamento"
        return Saida(f"ação '{r.acao}' ({r.motivo}) → {destino}",
                     dict(acao=r.acao, sinais=r.sinais, pergunta_sanitizada=r.pergunta_sanitizada))
