"""Tipo de documento e fase (RF03) no worker: regras do cabeçalho e, quando houver versão em uso, o modelo.

As regras e o pré-processamento são os do baseline da semana 2 (`treino/classificador_tipo.py`, decisão 0004) e
ficam aqui para o worker não depender do grupo de treino. Sem versão em uso do modelo, o worker usa as regras do
cabeçalho; sem cabeçalho reconhecível, **se abstém** (RNF04) em vez de adivinhar.
"""
from __future__ import annotations

import re
import unicodedata

CLASSES = ("recurso_ordinario", "agravo_peticao", "embargos_declaracao", "agravo_instrumento", "acao_originaria")
NOMES = {"recurso_ordinario": "recurso ordinário", "agravo_peticao": "agravo de petição",
         "embargos_declaracao": "embargos de declaração", "agravo_instrumento": "agravo de instrumento",
         "acao_originaria": "ação originária no tribunal"}
# Fase prevista a partir do tipo previsto. Agravo de instrumento e embargos dependem do recurso de origem: o
# baseline se abstém da fase nesses casos (RNF04) em vez de adivinhar.
FASE_DO_TIPO = {"recurso_ordinario": "conhecimento", "agravo_peticao": "execucao"}

MAX_CARACTERES = 30_000

_PADROES_CLASSE = [
    r"recursos?\s+ordin[aá]rios?",
    r"agravos?\s+de\s+peti[cç][aã]o",
    r"embargos\s+de\s+declara[cç][aã]o",
    r"embargos\s+declarat[oó]rios",
    r"agravos?\s+de\s+instrumento",
    r"mandados?\s+de\s+seguran[cç]a",
    r"a[cç][aã]o\s+rescis[oó]ria",
    r"habeas\s+corpus",
    r"conflito\s+de\s+compet[eê]ncia",
    r"remessa\s+necess[aá]ria",
    r"rito\s+sumar[ií]ssimo",
    r"diss[ií]dio\s+coletivo",
    r"\bagravante",
    r"\bagravad[oa]",
    r"\bembargante",
    r"\bembargad[oa]",
    r"\brecorrente",
    r"\brecorrid[oa]",
    r"\bimpetrante",
    r"\bimpetrad[oa]",
    r"\bsuscitante",
    r"\bsuscitad[oa]",
    r"\bexequente",
    r"\bexecutad[oa]",
]
_RE_CLASSE = re.compile("|".join(_PADROES_CLASSE), re.IGNORECASE)
_RE_CABECALHO = re.compile(r"^.*?\n\s*EMENTA\b", re.DOTALL)


# ---------------------------------------------------------------- funções puras (testadas no CI)

def sem_cabecalho(texto: str) -> str:
    """Remove o bloco de identificação até EMENTA e mascara nomes de classe e de papéis processuais."""
    t = _RE_CABECALHO.sub("EMENTA", texto[:MAX_CARACTERES], count=1)
    return _RE_CLASSE.sub(" CLASSEMASCARADA ", t)


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower()


# Ordem importa: embargos repetem no cabeçalho a classe do recurso embargado, então o papel "embargante" vem
# primeiro; agravo de instrumento antes de "recurso ordinário"/"agravo de petição", que aparecem no nome dele.
_REGRAS = [
    (r"\bembargantes?\b|embargos de declaracao|\bed\b", "embargos_declaracao"),
    (r"agravo de instrumento|\bairo\b|\baiap\b|\bai\b", "agravo_instrumento"),
    (r"agravo de peticao|\bap\b|\bagravantes?\b", "agravo_peticao"),
    (r"recurso ordinario|remessa necessaria|\brot\b|\brops\b|\bro\b|\brecorrentes?\b", "recurso_ordinario"),
    (
        r"mandado de seguranca|\bmsciv\b|\bms\b|\bimpetrantes?\b|acao rescisoria|\bar\b|habeas corpus"
        r"|conflito de competencia"
        r"|tutela (cautelar|antecipada)|dissidio coletivo|acao anulatoria|\bsuscitantes?\b|\bautor(es)?\b",
        "acao_originaria",
    ),
]
_RE_REGRAS = [(re.compile(p), tipo) for p, tipo in _REGRAS]


def regra_cabecalho(texto: str) -> str | None:
    """Baseline de regras: procura a classe ou o papel processual no bloco de identificação (antes de EMENTA).

    None = não encontrou (abstém)."""
    fim = texto.find("EMENTA", 0, 4000)
    alvo = _sem_acento(texto[: fim if fim > 0 else 2000])
    return next((tipo for padrao, tipo in _RE_REGRAS if padrao.search(alvo)), None)



def classificar(texto: str, modelo=None, limiar_abstencao: float = 0.44) -> dict:
    """{tipo, confianca_tipo, fase, confianca_fase, abstencao, metodo}. `modelo` = pipeline sklearn em uso (opcional)."""
    tipo: str | None
    if modelo is not None:
        proba = modelo.predict_proba([sem_cabecalho(texto)])[0]
        i = int(proba.argmax())
        tipo, conf = str(modelo.classes_[i]), float(proba[i])
        metodo = "modelo"
    else:
        tipo = regra_cabecalho(texto)
        conf, metodo = (0.9 if tipo else 0.0), "regras"
    abstem = tipo is None or conf < limiar_abstencao
    fase = FASE_DO_TIPO.get(tipo) if tipo and not abstem else None
    return {"tipo": None if abstem else tipo, "confianca_tipo": conf, "fase": fase,
            "confianca_fase": conf if fase else 0.0, "abstencao": abstem, "metodo": metodo}
