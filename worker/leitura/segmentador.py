"""Segmentador por regras (baseline do Eng. de dados): relatório, fundamentação, dispositivo e outro.

Reconhece os marcadores de **sentença** ("FUNDAMENTAÇÃO", "ANTE O EXPOSTO", "ISTO POSTO"…) e de **acórdão** do TRT
("EMENTA", "RELATÓRIO", "VOTO", "ADMISSIBILIDADE", "CONCLUSÃO", "ACÓRDÃO", "ACORDAM"…). O marcador vale do bloco em
que aparece até o próximo marcador. Num acórdão, o que vem antes do primeiro marcador (cabeçalho com classe, relator
e partes) e a ementa ficam como `outro`; a sentença sem cabeçalho começa como `relatorio`, como antes.

`parte_por_marcador` é pura e também gera os rótulos fracos de `treino/segmentador.py`.
"""
from __future__ import annotations

import re

from contratos import DocumentoLido, Segmentos, Trecho
from contratos.segmentos import Parte

_NUM = r"(?:[IVX]+\s*[-–.)]\s*|\d+\s*[-–.)]\s*|\(\d+\)\s*)?"

MARCADORES_OUTRO = re.compile(
    rf"^\s*{_NUM}(EMENTA\b|IDENTIFICA[ÇC][ÃA]O\b|DECLARA[ÇC][ÃA]O DE VOTO\b|CABE[ÇC]ALHO DO AC[ÓO]RD[ÃA]O\b"
    r"|PODER JUDICI[ÁA]RIO\b)", re.I)
MARCADORES_RELATORIO = re.compile(rf"^\s*{_NUM}RELAT[ÓO]RIO\b", re.I)
MARCADORES_FUNDAMENTACAO = re.compile(
    rf"^\s*{_NUM}(FUNDAMENTA[ÇC][ÃA]O|FUNDAMENTOS\s*$|V\s?O\s?T\s?O\s*$|ADMISSIBILIDADE\b|M[ÉE]RITO\b)", re.I)
# Sentença: as fórmulas de fecho abrem o dispositivo. Acórdão: só o título em linha própria ("CONCLUSÃO", "ACÓRDÃO",
# "ACORDAM"), porque "Ante o exposto, nego provimento…" fecha cada tópico do voto e "Conclusão da admissibilidade" e
# "IV. DISPOSITIVO E TESE" (ementa no formato novo) são subtítulos.
MARCADORES_DISPOSITIVO = re.compile(r"^\s*(ANTE O EXPOSTO|DISPOSITIVO|ISTO POSTO|DIANTE DO EXPOSTO)", re.I)
MARCADORES_DISPOSITIVO_ACORDAO = re.compile(
    rf"^\s*{_NUM}(CONCLUS[ÃA]O|DISPOSITIVO|AC[ÓO]RD[ÃA]O)\s*:?\s*$|^\s*(ACORDAM|POR TAIS FUNDAMENTOS)\b", re.I)


def _primeira_linha(texto: str) -> str:
    return texto.strip().split("\n", 1)[0].strip()


def parte_por_marcador(texto: str, atual: Parte, acordao: bool = True) -> Parte | None:
    """Parte aberta por um marcador no início do texto, ou None se o texto não começa com marcador."""
    primeira = _primeira_linha(texto)
    if (MARCADORES_DISPOSITIVO_ACORDAO if acordao else MARCADORES_DISPOSITIVO).search(primeira):
        return "dispositivo"
    if MARCADORES_OUTRO.search(primeira):
        return "outro"
    if MARCADORES_RELATORIO.search(primeira):
        return "relatorio"
    if MARCADORES_FUNDAMENTACAO.search(primeira):
        # "MÉRITO"/"ADMISSIBILIDADE" depois da conclusão é subtítulo, não volta à fundamentação
        return None if atual == "dispositivo" else "fundamentacao"
    return None


def e_acordao(textos: list[str]) -> bool:
    return any(MARCADORES_OUTRO.search(_primeira_linha(t)) for t in textos[:15])


def segmentar(doc: DocumentoLido) -> Segmentos:
    blocos = [b for p in doc.paginas for b in p.blocos]
    acordao = e_acordao([b.texto for b in blocos])
    parte: Parte = "outro" if acordao else "relatorio"
    trechos = []
    for bloco in blocos:
        parte = parte_por_marcador(bloco.texto, parte, acordao) or parte
        trechos.append(Trecho(id=bloco.id, parte=parte, texto=bloco.texto, posicoes=[bloco.posicao]))
    return Segmentos(tarefa_id=doc.tarefa_id, metodo="regras", trechos=trechos)
