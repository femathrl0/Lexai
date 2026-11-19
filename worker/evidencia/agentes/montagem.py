"""Monta o sistema multiagente com os componentes reais (usado pela CLI de demo e pelo worker)."""
from __future__ import annotations

import os
from pathlib import Path

from .analise import AgenteAnalise
from .comunicacao import AgenteComunicacao
from .llm import ClienteOllama
from .orquestrador import Orquestrador
from .pesquisa import AgentePesquisa
from .triagem import AgenteTriagem
from .validacao import AgenteValidacao

# Recorte de jurisprudência anonimizado (Eng. de dados): entra por padrão no buscador local quando existe.
JURISPRUDENCIA_PADRAO = Path(__file__).resolve().parents[3] / "corpus" / "jurisprudencia" / "recorte_demo.jsonl"


def montar(buscador: str = "local", modelo: str | None = None, nli: bool = True, reranker: bool = True,
           jurisprudencia: str | None = None, device: str | None = None, **kw) -> Orquestrador:
    llm = ClienteOllama(modelo)
    if buscador == "pgvector":
        from .buscadores import BuscadorPgvector
        busca = BuscadorPgvector(os.environ["DATABASE_URL_LEGADO"], device=device or "cpu")
    else:
        from .buscadores import BuscadorLocal
        if jurisprudencia is None and JURISPRUDENCIA_PADRAO.exists():
            jurisprudencia = str(JURISPRUDENCIA_PADRAO)
        busca = BuscadorLocal(jurisprudencia=jurisprudencia or None, usar_reranker=reranker, device=device)
    verificador = None
    if nli:
        from worker.evidencia.verificador import VerificadorNLI
        verificador = VerificadorNLI(device=device)
    return Orquestrador(
        AgenteTriagem(), AgentePesquisa(busca, llm=llm), AgenteAnalise(llm), AgenteComunicacao(llm),
        AgenteValidacao(verificador, versoes_extra=dict(buscador=busca.versao)), **kw)
