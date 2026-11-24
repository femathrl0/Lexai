"""Componentes simulados: os testes dos agentes rodam no CI sem Ollama, banco ou modelos."""
from __future__ import annotations

import re

from contratos import TrechoEvidencia
from worker.evidencia.agentes.analise import AgenteAnalise, ExplicacaoLLM
from worker.evidencia.agentes.comunicacao import AgenteComunicacao, ComunicacaoLLM
from worker.evidencia.agentes.orquestrador import Orquestrador
from worker.evidencia.agentes.pesquisa import AgentePesquisa, ConsultaReformulada
from worker.evidencia.agentes.triagem import AgenteTriagem
from worker.evidencia.agentes.validacao import AgenteValidacao

T477 = TrechoEvidencia(id="lei:477", indice="corpus_juridico", tipo_fonte="lei", fonte="CLT, Art. 477",
                       texto="Na extinção do contrato de trabalho, o empregador deverá pagar as verbas rescisórias em até "
                             "dez dias contados a partir do término do contrato.", versao="teste", nota_reranker=0.9)
T487 = TrechoEvidencia(id="lei:487", indice="corpus_juridico", tipo_fonte="lei", fonte="CLT, Art. 487",
                       texto="Não havendo prazo estipulado, a parte que quiser rescindir o contrato deverá avisar a outra "
                             "com antecedência mínima de trinta dias.", versao="teste", nota_reranker=0.7)


class LLMFalsa:
    modelo = "falso"

    def __init__(self, explicacoes: list[list[dict]], comunicacao=None):
        self.explicacoes = list(explicacoes)
        self.comunicacao = comunicacao or (lambda ordem, texto: f"Em palavras simples: {texto}")
        self.chamadas: list[str] = []
        self.ultimo_usuario: dict[str, str] = {}

    def gerar(self, sistema, usuario, formato):
        self.chamadas.append(formato.__name__)
        self.ultimo_usuario[formato.__name__] = usuario
        if formato is ExplicacaoLLM:
            return ExplicacaoLLM.model_validate(dict(frases=self.explicacoes.pop(0)))
        if formato is ComunicacaoLLM:
            frases = re.findall(r"^(\d+)\. (.*)$", usuario, re.M)
            return ComunicacaoLLM(frases=[dict(ordem=int(o), texto=self.comunicacao(int(o), t)) for o, t in frases])
        if formato is ConsultaReformulada:
            return ConsultaReformulada(consulta="verbas rescisórias art. 477 CLT")
        raise AssertionError(formato)


class BuscadorFalso:
    versao = "falso:1"

    def __init__(self, respostas: list[list[TrechoEvidencia]] | None = None):
        self.respostas = respostas
        self.consultas: list[str] = []

    def buscar(self, consulta, por_fonte=3):
        self.consultas.append(consulta)
        if self.respostas is not None:
            return self.respostas.pop(0)
        return [T477, T487]


class VerificadorFalso:
    """Sustenta quando a frase compartilha um número com o trecho; frases com 'inventad' nunca são sustentadas."""

    modelo = "nli-falso"

    def verificar(self, frase, trecho):
        if "inventad" in frase:
            return "nao_trata", dict(sustenta=0.05, nao_trata=0.9, contradiz=0.05)
        if "vinte dias" in frase:
            return "contradiz", dict(sustenta=0.02, nao_trata=0.08, contradiz=0.9)
        return "sustenta", dict(sustenta=0.95, nao_trata=0.04, contradiz=0.01)


def sistema(explicacoes, buscador=None, verificador=None, eventos=None, **kw):
    llm = LLMFalsa(explicacoes, **kw)
    busca = buscador or BuscadorFalso()
    orq = Orquestrador(AgenteTriagem(), AgentePesquisa(busca, llm=llm), AgenteAnalise(llm), AgenteComunicacao(llm),
                       AgenteValidacao(verificador or VerificadorFalso()),
                       publicar=(eventos.append if eventos is not None else None))
    return orq, llm, busca
