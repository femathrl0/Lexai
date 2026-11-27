"""Extrator de campos (issue #24, RF02): número do processo, classe, relator, turma, data do julgamento, papéis das
partes, valores e pedidos (tópicos da ementa).

Baseline por regras (decisão 0004: regras primeiro). Privacidade (RNF01): **nunca devolve nome de parte nem de
advogado** — das partes sai só o papel ("recorrente: reclamante"); o relator é autoridade pública e aparece. Campo não
encontrado volta com `valor=None` ("não identificado"), nunca adivinhado.

Cada campo leva uma confiança fixa por regra (regex com âncora forte = alta; heurística = média), para o app mostrar
"confira no documento" abaixo do limiar.
"""
from __future__ import annotations

import re
import unicodedata

from contratos import Campo

PROCESSO_CNJ = re.compile(r"(?<!\d)(\d{7}-?\d{2}\.?\d{4}\.?\d\.?\d{2}\.?\d{4})(?!\d)")
_CLASSES = re.compile(
    r"\b(RECURSO ORDIN[ÁA]RIO(?: (?:TRABALHISTA|EM PROCEDIMENTO SUMAR[ÍI]SSIMO|- RITO SUMAR[ÍI]SSIMO))?|AGRAVO DE PETI[ÇC][ÃA]O"
    r"|AGRAVO DE INSTRUMENTO(?: EM (?:RECURSO ORDIN[ÁA]RIO|AGRAVO DE PETI[ÇC][ÃA]O))?|EMBARGOS DE DECLARA[ÇC][ÃA]O"
    r"|MANDADO DE SEGURAN[ÇC]A|A[ÇC][ÃA]O RESCIS[ÓO]RIA|\bROT?\b|\bROPS\b|\bAP\b|\bED\b|\bAIRO\b|\bAIAP\b)", re.I)
_RELATOR = re.compile(r"RELATOR\(?A?\)?\s*:\s*(?:JU[IÍ]Z[AO]?|DESEMBARGADOR[AE]?|DES\.?)?\s*(?:CONVOCAD[AO]\s*)?"
                      r"([A-ZÁÂÃÉÊÍÓÔÕÚÇ][A-ZÁÂÃÉÊÍÓÔÕÚÇ .'-]{4,80})", re.I)
_TURMA = re.compile(r"\b(\d)ª\s*TURMA\b|\b(PRIMEIRA|SEGUNDA|TERCEIRA)\s+TURMA\b|\bTRIBUNAL PLENO\b", re.I)
_MESES = {m: i for i, m in enumerate(("janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto",
                                      "setembro", "outubro", "novembro", "dezembro"), start=1)}
_DATA_EXTENSO = re.compile(r"(\d{1,2})\s*(?:º|o)?\s+de\s+([a-zç]+)\s+de\s+(\d{4})\s*\.?\s*\(data d[oe] julgamento\)", re.I)
_DATA_JULGADO = re.compile(r"(?:julgamento|julgado em|sess[ãa]o (?:ordin[áa]ria|virtual)? ?(?:realizada )?em)\s*:?\s*"
                           r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})", re.I)
_VALOR = re.compile(r"R\$\s?(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)")
_PAPEL = re.compile(r"^\s*(RECORRENTE|RECORRID[OA]|AGRAVANTE|AGRAVAD[OA]|EMBARGANTE|EMBARGAD[OA]|IMPETRANTE|IMPETRAD[OA])S?\s*:",
                    re.I | re.M)
_RECLAMANTE = re.compile(
    r"\brecurso (?:ordin[áa]rio )?(?:interposto )?(?:d[oa]s?|pel[oa]s?) (reclamante|autor[a]?|obreir[oa])", re.I)
_RECLAMADA = re.compile(r"\brecurso (?:ordin[áa]rio )?(?:interposto )?(?:d[oa]s?|pel[oa]s?) (reclamad[oa]s?|r[ée]s?|empresa"
                        r"|empregador[a]?|patronal|uni[ãa]o|munic[íi]pio|distrito federal)", re.I)
_TOPICO_EMENTA = re.compile(r"^\s*(?:[-–•]|\d+\.)?\s*([A-ZÁÂÃÉÊÍÓÔÕÚÇ][A-ZÁÂÃÉÊÍÓÔÕÚÇ ,/()º-]{3,80}?)\s*[.:]", re.M)
_NAO_PEDIDO = re.compile(r"^(RECURSO|EMENTA|AGRAVO|EMBARGOS|ADMISSIBILIDADE|CONHECIMENTO|PRELIMINAR|M[ÉE]RITO|TRT|TST|CLT"
                         r"|CASO EM EXAME|QUEST[ÃA]O EM DISCUSS[ÃA]O|RAZ[ÕO]ES DE DECIDIR|DISPOSITIVO|TESE|I+V?|V"
                         r"|DA|DO|DAS|DOS|DE|ART|ARTS|ANALISE|PARTE|SUMULA|OJ|LEI|SENTENCA|ACORDAO|RELATOR|NOS TERMOS)\b")


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def cabecalho(texto: str) -> str:
    fim = texto.find("EMENTA", 0, 6000)
    return texto[: fim if fim > 0 else 3000]


def ementa(texto: str) -> str:
    ini = texto.find("EMENTA")
    if ini < 0:
        return ""
    fim = min([i for i in (texto.find("RELATÓRIO", ini), texto.find("RELATORIO", ini)) if i > 0] or [ini + 6000])
    return texto[ini + len("EMENTA"): fim]


def numero_processo(texto: str) -> str | None:
    m = PROCESSO_CNJ.search(cabecalho(texto)) or PROCESSO_CNJ.search(texto[:20000])
    if not m:
        return None
    d = re.sub(r"\D", "", m.group(1))
    return f"{d[:7]}-{d[7:9]}.{d[9:13]}.{d[13]}.{d[14:16]}.{d[16:20]}"


def relator(texto: str) -> str | None:
    m = _RELATOR.search(cabecalho(texto)) or _RELATOR.search(texto[:6000])
    if not m:
        return None
    nome = re.split(r"\s{2,}|\n|\bRECORRENTE|\bAGRAVANTE|\bEMBARGANTE|\bIMPETRANTE", m.group(1))[0]
    return " ".join(nome.split()).upper() or None


def data_julgamento(texto: str) -> str | None:
    t = _sem_acento(texto[-6000:])
    if m := _DATA_EXTENSO.search(t):
        mes = _MESES.get(m.group(2).lower())
        if mes:
            return f"{int(m.group(3)):04d}-{mes:02d}-{int(m.group(1)):02d}"
    if m := _DATA_JULGADO.search(t):
        return f"{int(m.group(3)):04d}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    return None


def pedidos(texto: str, maximo: int = 12) -> list[str]:
    """Títulos dos tópicos da ementa ("HORAS EXTRAS", "DANO MORAL"…) — cada um é um pedido em discussão."""
    vistos: list[str] = []
    for m in _TOPICO_EMENTA.finditer(ementa(texto)):
        t = " ".join(m.group(1).split()).strip(" ,-")
        if len(t) < 4 or _NAO_PEDIDO.match(_sem_acento(t).upper()) or t in vistos:
            continue
        vistos.append(t)
    return vistos[:maximo]


def recorrentes(texto: str) -> list[str]:
    """Quem recorreu, só pelo papel processual (sem nome)."""
    t = texto[:40000]
    quem = []
    if _RECLAMANTE.search(t):
        quem.append("reclamante")
    if _RECLAMADA.search(t):
        quem.append("reclamada")
    return quem


def extrair(texto: str, trecho_id: str | None = None) -> list[Campo]:
    cab = cabecalho(texto)
    classe = _CLASSES.search(cab)
    turma = _TURMA.search(cab) or _TURMA.search(texto[:6000])
    valores = sorted({v for v in _VALOR.findall(texto)}, key=lambda v: float(v.replace(".", "").replace(",", ".")))
    papeis = sorted({_sem_acento(p.group(1)).lower().rstrip("s") for p in _PAPEL.finditer(cab)})
    peds = pedidos(texto)
    quem = recorrentes(texto)
    num, rel, data = numero_processo(texto), relator(texto), data_julgamento(texto)

    def campo(nome, valor, conf):
        return Campo(nome=nome, valor=valor, confianca=conf if valor else 0.0, trecho_id=trecho_id)

    return [
        campo("numero_processo", num, 0.99),
        campo("classe", " ".join(classe.group(1).split()).upper() if classe else None, 0.9),
        campo("relator", rel, 0.85),
        campo("orgao_julgador", " ".join(turma.group(0).split()).upper() if turma else None, 0.8),
        campo("data_julgamento", data, 0.9),
        campo("papeis_partes", ", ".join(papeis) or None, 0.9),
        campo("recorrentes", ", ".join(quem) or None, 0.6),
        campo("valores_citados", "; ".join(f"R$ {v}" for v in valores[-5:]) or None, 0.7),
        campo("pedidos", "; ".join(peds) or None, 0.6),
    ]


def como_dict(campos: list[Campo]) -> dict[str, str | None]:
    return {c.nome: c.valor for c in campos}
