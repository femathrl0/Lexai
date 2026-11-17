from __future__ import annotations

from contratos import FraseAprovada, RespostaVerificada, Versoes
from contratos.agentes import EstadoTarefa
from worker.evidencia import guardas
from worker.evidencia.verificador import Verificador

from .base import Agente, Saida

# Frases que dão ordens à pessoa sobre o caso (manual: guarda de saída). Encaminhamento genérico é permitido.
CONSELHO = guardas._rx(r"\bvoce (deve|precisa|tem que|deveria)\b", r"\brecorra\b", r"\bprocesse\b",
                       r"\bentre com (uma )?(acao|processo|reclamacao)\b", r"\bexija\b", r"\bnao assine\b",
                       r"\baceite o acordo\b", r"\bvale a pena (processar|entrar)\b")
JANELA = 1200  # caracteres por janela do trecho; artigos longos passam do limite de 512 tokens do NLI


def _janelas(texto: str) -> list[str]:
    if len(texto) <= JANELA:
        return [texto]
    passo = JANELA - 200
    return [texto[i:i + JANELA] for i in range(0, len(texto) - 200, passo)]


class AgenteValidacao(Agente):
    nome = "validacao"
    responsabilidade = ("Validation Agent: último portão. Confere cada frase contra o trecho citado (NLI: sustenta, "
                        "contradiz ou não trata) e contra as regras de saída (sem fonte, conselho, promessa, dado "
                        "pessoal); devolve frases reprovadas para reescrita (1×), pede nova busca se faltar fonte (1×) "
                        "e, no fim, remove o que segue reprovado e emite avisos de incerteza.")

    def __init__(self, verificador: Verificador | None, limiar_sustenta: float = 0.5, versoes_extra: dict | None = None):
        self.verificador, self.limiar = verificador, limiar_sustenta
        self.versoes_extra = versoes_extra or {}

    def _julgar(self, texto: str, trecho) -> tuple[bool, str, dict]:
        base = guardas._sem_acento(texto)
        if trecho is None:
            return False, "frase sem trecho de apoio", {}
        if CONSELHO.search(base):
            return False, "dá ordem à pessoa sobre o caso (aconselhamento)", {}
        if guardas.PROMESSA.search(base):
            return False, "promete resultado", {}
        if self.verificador is None:
            return True, "aprovada só pelas regras (NLI desligado)", {}
        melhor, probs_melhor = None, {}
        for janela in _janelas(trecho.texto):
            veredito, probs = self.verificador.verificar(texto, janela)
            if not probs_melhor or probs["sustenta"] > probs_melhor["sustenta"]:
                melhor, probs_melhor = veredito, probs
        if probs_melhor["sustenta"] >= self.limiar:
            return True, f"sustentada pelo trecho (p={probs_melhor['sustenta']:.2f})", probs_melhor
        motivo = "o trecho contradiz a frase" if melhor == "contradiz" else "o trecho citado não trata do que a frase afirma"
        return False, f"{motivo} (p_sustenta={probs_melhor['sustenta']:.2f})", probs_melhor

    def executar(self, estado: EstadoTarefa) -> Saida:
        por_id = {t.id: t for t in estado.evidencias.trechos}
        aprovadas, reprovadas, julgamento = [], {}, []
        for f in estado.explicacao.frases:
            trecho = por_id.get(f.trecho_id) if f.trecho_id else None
            ok, motivo, probs = self._julgar(f.texto, trecho)
            julgamento.append(dict(ordem=f.ordem, aprovada=ok, motivo=motivo, nli=probs, trecho=f.trecho_id))
            if ok:
                texto, _ = guardas.mascarar(f.texto)
                aprovadas.append(FraseAprovada(ordem=f.ordem, texto=texto, trecho_id=trecho.id, fonte=trecho.fonte))
            else:
                reprovadas[f.ordem] = motivo
        dados = dict(julgamento=julgamento, limiar_sustenta=self.limiar,
                     verificador=getattr(self.verificador, "modelo", None))

        if reprovadas and estado.reescritas < 1:
            estado.reescritas += 1
            estado.frases_para_refazer = reprovadas
            return Saida(f"{len(aprovadas)} aprovadas, {len(reprovadas)} reprovadas → devolve à Análise para reescrever "
                         f"as frases {sorted(reprovadas)}", dados, tipo="devolucao", devolver_para="analise")
        sem_fonte = estado.evidencias.sem_fonte_segura or all("sem trecho" in m for m in reprovadas.values())
        if not aprovadas and sem_fonte and estado.novas_buscas < 1:
            estado.novas_buscas += 1
            estado.frases_para_refazer = {}
            return Saida("nenhuma frase com fonte → pede à Pesquisa uma nova busca com consulta reformulada", dados,
                         tipo="devolucao", devolver_para="pesquisa")

        avisos = []
        if reprovadas:
            avisos.append(f"{len(reprovadas)} frase(s) foram removidas porque não puderam ser confirmadas nas fontes.")
        if not aprovadas:
            avisos.append("Não encontrei fonte jurídica segura para responder. Explico só o que está nas fontes, e aqui "
                          "elas não bastaram.")
        if estado.triagem.acao == "orientar_sem_aconselhar":
            avisos.append("Sua pergunta descreve um caso concreto: procure um advogado, a Defensoria Pública ou o "
                          "sindicato da categoria para avaliar a sua situação.")
        avisos.append(guardas.AVISO_LEGAL)
        estado.resposta = RespostaVerificada(
            tarefa_id=estado.tarefa_id, frases=aprovadas, avisos=avisos,
            versoes=Versoes(modelos={k: v for k, v in dict(llm=estado.explicacao.modelo_llm,
                                                            nli=dados["verificador"], **self.versoes_extra).items() if v},
                            prompt=estado.explicacao.prompt_id, indices={"corpus_juridico": estado.evidencias.trechos[0].versao}
                            if estado.evidencias.trechos else {}))
        return Saida(f"liberou {len(aprovadas)} frases" + (f", removeu {len(reprovadas)}" if reprovadas else ""), dados)
