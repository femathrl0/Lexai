"""Expansão da consulta: vocabulário do trabalhador → vocabulário da lei (Agente de Pesquisa).

A pessoa pergunta "quais verbas recebo na demissão e em quanto tempo"; o art. 477 da CLT fala em "extinção do
contrato", "verbas rescisórias" e "prazo". A busca por palavra-chave não liga as duas coisas e o vetor nem sempre
compensa. A expansão acrescenta (nunca remove) os termos técnicos equivalentes antes da busca. É determinística,
testável sem modelos e revisável pela Curadoria: cada regra é um par (padrão leigo, termos da lei).

A reformulação por LLM continua existindo, mas só na nova busca pedida pela Validação.
"""
from __future__ import annotations

import re
import unicodedata


def _sem_acento(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


# (padrão sobre a pergunta sem acento, termos acrescentados). Ordem não importa; termos repetidos saem uma vez.
REGRAS: list[tuple[str, str]] = [
    (r"\b(demiss\w*|demitid\w*|mandad\w* embora|dispensad\w*|despedid\w*)\b",
     "extinção do contrato de trabalho rescisão dispensa"),
    (r"\bverbas?\b|\b(o que|quanto) (eu )?recebo\b|\bacerto\b",
     "verbas rescisórias pagamento das parcelas instrumento de rescisão"),
    (r"\bem quanto tempo\b|\bprazo\b|\bquando (eu )?(recebo|devo receber|vou receber)\b|\bate quando\b",
     "prazo pagamento dias contados"),
    (r"\b(gravid\w*|gestante|gestacao|engravid\w*)\b",
     "empregada gestante estabilidade provisória confirmação da gravidez dispensa arbitrária"),
    (r"\baviso\b", "aviso prévio proporcional tempo de serviço"),
    (r"\bfgts\b|\bfundo de garantia\b", "FGTS conta vinculada depósito rescisão"),
    (r"\bhora extra\b|\bhoras extras\b", "horas suplementares jornada acréscimo"),
    (r"\bnoturn\w*\b|\bde noite\b", "trabalho noturno adicional hora noturna"),
    (r"\bferias\b", "férias proporcionais remuneração das férias"),
    (r"\b13o?\b|\bdecimo terceiro\b", "gratificação de natal décimo terceiro salário"),
    (r"\bdesconto\w*\b", "descontos no salário"),
    (r"\bcarteira (de trabalho|assinada)\b", "Carteira de Trabalho e Previdência Social anotação"),
]
_COMPILADAS = [(re.compile(p), termos) for p, termos in REGRAS]


def expandir(consulta: str) -> tuple[str, list[str]]:
    """Devolve (consulta expandida, termos acrescentados). Sem regra aplicável, devolve a consulta original."""
    base = _sem_acento(consulta)
    acrescentar: list[str] = []
    for padrao, termos in _COMPILADAS:
        if padrao.search(base):
            for t in termos.split():
                if _sem_acento(t) not in base and t not in acrescentar:
                    acrescentar.append(t)
    if not acrescentar:
        return consulta, []
    return f"{consulta} {' '.join(acrescentar)}", acrescentar
