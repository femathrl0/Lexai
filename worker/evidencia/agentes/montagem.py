"""Monta o sistema multiagente com os componentes reais (usado pela CLI de demo e pelo worker)."""
from __future__ import annotations

import os

from .analise import AgenteAnalise
from .comunicacao import AgenteComunicacao
from .llm import ClienteOllama
from .orquestrador import Orquestrador
from .pesquisa import AgentePesquisa
from .triagem import AgenteTriagem
from .validacao import AgenteValidacao


def montar(buscador: str = "local", modelo: str | None = None, nli: bool = True, reranker: bool = True,
           jurisprudencia: str | None = None, device: str | None = None, **kw) -> Orquestrador:
    llm = ClienteOllama(modelo)
    if buscador == "pgvector":
        from .buscadores import BuscadorPgvector
        busca = BuscadorPgvector(os.environ["DATABASE_URL_LEGADO"], device=device or "cpu")
    else:
        from .buscadores import BuscadorLocal
        busca = BuscadorLocal(jurisprudencia=jurisprudencia, usar_reranker=reranker, device=device)
    verificador = None
    if nli:
        from worker.evidencia.verificador import VerificadorNLI
        verificador = VerificadorNLI(device=device)
    return Orquestrador(
        AgenteTriagem(), AgentePesquisa(busca, llm=llm), AgenteAnalise(llm), AgenteComunicacao(llm),
        AgenteValidacao(verificador, versoes_extra=dict(buscador=busca.versao)), **kw)
