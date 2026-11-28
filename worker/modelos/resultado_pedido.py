"""Resultado no worker (issue #24, RF03): do recurso (conclusão do voto) e de cada pedido (tópicos da ementa).

Baseline por regras, em uso pela decisão 0004 (venceu o TF-IDF + LR no rótulo prata: `treino/relatorios/
resultado_pedido.md`). O erro que importa é a troca entre ganhar e perder; por isso, quando a fórmula não é clara, o
resultado é `nao_identificado` com confiança 0 (o app diz "confira no documento"), nunca um palpite.

- **Recurso**: provido, parcialmente provido, desprovido ou não conhecido (`classificar_regra`).
- **Pedido**: cada tópico da ementa ("HORAS EXTRAS: … DEVIDAS") vira um `ResultadoPedido` procedente, improcedente ou
  parcialmente procedente quando o tópico diz o resultado do direito em si (devido/indevido, deferido/indeferido,
  reconhecido/não configurado). "Sentença mantida" sozinho não diz quem ganhou: fica `nao_identificado`.
"""
from __future__ import annotations

import re
import unicodedata

from contratos import ResultadoPedido
from contratos.classificacao import Resultado


def _norm(s: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", s)


# formas impessoais (ACORDAM: "negar provimento") e de 1ª pessoa (conclusão: "nego provimento")
_NEGA = re.compile(r"\b(negar|nego|negam|nega|negou|negaram)(-lhe|-lhes)? provimento|\bdesprovid[oa]s?\b|\bdesprovimento\b")
_PARCIAL = re.compile(r"\b(dar|dou|dao|deu|deram)(-lhe|-lhes)? (parcial provimento|provimento parcial)"
                      r"|\bparcialmente provid[oa]s?\b|\bprovimento parcial\b|\bparcial provimento\b")
_DA = re.compile(r"\b(dar|dou|dao|deu|deram)(-lhe|-lhes)? provimento\b|(?<!des)(?<!parcialmente )\bprovid[oa]s?\b")
_NAO_CONHECE = re.compile(r"\bnao (conhecer|conheco|conhecem|conheceu|conhecido)\b")


def classificar_regra(texto: str) -> str | None:
    """Resultado pela fórmula. None = misto (resultados diferentes para recursos diferentes) ou não encontrado."""
    t = _norm(texto)
    achados = set()
    if _PARCIAL.search(t):
        achados.add("parcialmente_provido")
    sem_parcial = _PARCIAL.sub(" ", t)
    if _NEGA.search(sem_parcial):
        achados.add("desprovido")
    if _DA.search(_NEGA.sub(" ", sem_parcial)):
        achados.add("provido")
    if not achados and _NAO_CONHECE.search(t):
        return "nao_conhecido"
    return achados.pop() if len(achados) == 1 else None


_RE_ACORDAM = re.compile(r"\n\s*ACORDAM\b(.{0,3000}?)(?:\n\s*\n\s*[A-Z][^\n]{0,60}\(DF\)|\n\s*Bras[ií]lia|\Z)", re.S)
_RE_CONCLUSAO = re.compile(r"\n\s*(?:[IVX]+\s*[-–.)]\s*|\d+\s*[-–.)]\s*|\(\d+\)\s*)?CONCLUS[ÃA]O\s*:?\s*\n(.{0,4000}?)"
                           r"(?:\n\s*[ÉE] (?:o|como) voto|\n\s*AC[ÓO]RD[ÃA]O\s*\n|\Z)", re.S | re.I)


def trecho_acordam(texto: str) -> str | None:
    m = _RE_ACORDAM.search(texto)
    return m.group(1).strip() if m else None


def trecho_conclusao(texto: str) -> str | None:
    m = _RE_CONCLUSAO.search(texto)
    return m.group(1).strip() if m else None



_PARCIAL_PEDIDO = re.compile(r"\b(parcialmente (procedente|devid|deferid)|em parte|parcialmente)\b")
_IMPROCEDE = re.compile(r"\b(indevid[oa]s?|indeferid[oa]s?|improceden(te|tes|cia)|nao (configurad|reconhecid|caracterizad|"
                        r"comprovad|devid)\w*|afastad[oa]s?|exclu[ií]d[oa]s?|inexist[eê]ncia|nao cabimento|incabivel|"
                        r"absolvi\w*)")
_PROCEDE = re.compile(r"\b(devid[oa]s?|deferid[oa]s?|procedente|reconhecid[oa]s?|configurad[oa]s?|caracterizad[oa]s?|"
                      r"condenacao mantida|cabimento|mantida a condenacao|majorad[oa]s?)\b")


def resultado_do_topico(texto: str) -> tuple[Resultado, float]:
    t = _norm(texto)
    if _PARCIAL_PEDIDO.search(t):
        return "parcialmente_procedente", 0.6
    neg, pos = bool(_IMPROCEDE.search(t)), bool(_PROCEDE.search(_IMPROCEDE.sub(" ", t)))
    if neg and not pos:
        return "improcedente", 0.7
    if pos and not neg:
        return "procedente", 0.7
    return "nao_identificado", 0.0


_TOPICOS = re.compile(r"(?:^|\n)\s*(?:[-–•]|\d+\.)?\s*([A-ZÁÂÃÉÊÍÓÔÕÚÇ][A-ZÁÂÃÉÊÍÓÔÕÚÇ ,/()º-]{3,80}?)\s*[.:](.*?)"
                      r"(?=\n\s*(?:[-–•]|\d+\.)?\s*[A-ZÁÂÃÉÊÍÓÔÕÚÇ][A-ZÁÂÃÉÊÍÓÔÕÚÇ ,/()º-]{3,80}?\s*[.:]|\Z)", re.S)


def pedidos_da_ementa(ementa: str, limiar_abstencao: float = 0.5, trecho_id: str | None = None) -> list[ResultadoPedido]:
    from worker.modelos.extrator_campos import _NAO_PEDIDO, _sem_acento

    saida, vistos = [], set()
    for m in _TOPICOS.finditer(ementa):
        pedido = " ".join(m.group(1).split()).strip(" ,-")
        if len(pedido) < 4 or _NAO_PEDIDO.match(_sem_acento(pedido).upper()) or pedido in vistos:
            continue
        vistos.add(pedido)
        resultado, conf = resultado_do_topico(m.group(2))
        if conf < limiar_abstencao:
            resultado, conf = "nao_identificado", 0.0
        saida.append(ResultadoPedido(pedido=pedido, resultado=resultado, confianca=conf, trecho_id=trecho_id))
    return saida
