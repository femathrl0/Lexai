"""Segmentador por regras (baseline do Eng. de dados): relatório, fundamentação e dispositivo."""
import re

from contratos import DocumentoLido, Segmentos, Trecho

MARCADORES_FUNDAMENTACAO = re.compile(r"^\s*(FUNDAMENTA[ÇC][ÃA]O|II\s*[-–]\s*FUNDAMENTA)", re.I)
MARCADORES_DISPOSITIVO = re.compile(r"^\s*(ANTE O EXPOSTO|DISPOSITIVO|ISTO POSTO|DIANTE DO EXPOSTO)", re.I)


def segmentar(doc: DocumentoLido) -> Segmentos:
    parte = "relatorio"
    trechos = []
    for pagina in doc.paginas:
        for bloco in pagina.blocos:
            if MARCADORES_DISPOSITIVO.search(bloco.texto):
                parte = "dispositivo"
            elif parte == "relatorio" and MARCADORES_FUNDAMENTACAO.search(bloco.texto):
                parte = "fundamentacao"
            trechos.append(Trecho(id=bloco.id, parte=parte, texto=bloco.texto, posicoes=[bloco.posicao]))
    return Segmentos(tarefa_id=doc.tarefa_id, metodo="regras", trechos=trechos)
