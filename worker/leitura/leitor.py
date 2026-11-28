"""Leitor (Eng. de dados): PDF nativo -> DocumentoLido, guardando página e posição de cada bloco.

Limpeza (bloqueio da #22, feita aqui para o fluxo do documento da semana 4):
- **cabeçalho e rodapé**: bloco que se repete (normalizado, sem números) no topo ou no pé de ao menos metade das
  páginas, e número de página solto, saem do texto;
- **hifenização**: "presta-\\nção" vira "prestação" (só quando a quebra é no fim da linha e a palavra segue em
  minúscula, para não juntar "art. 7º-\\nA");
- PDF sem texto nativo volta com qualidade 0 (o OCR entra na semana 5).
"""
from __future__ import annotations

import re
from collections import Counter

from contratos import Bloco, DocumentoLido, Pagina
from contratos.base import Posicao

_HIFEN = re.compile(r"(\w)-\n(?=[a-zà-ú])")
_NUM_PAGINA = re.compile(r"^\s*(p[áa]g(ina)?\.?\s*)?\d{1,4}(\s*(/|de)\s*\d{1,4})?\s*$", re.I)
_DIGITOS = re.compile(r"\d+")
FAIXA_MARGEM = 0.12  # fração da altura da página considerada topo/pé


def desfazer_hifenizacao(texto: str) -> str:
    return _HIFEN.sub(r"\1", texto)


def _assinatura(texto: str) -> str:
    return _DIGITOS.sub("#", " ".join(texto.lower().split()))


def repetidos_nas_margens(paginas: list[list[tuple[str, float, float]]], minimo: float = 0.5) -> set[str]:
    """Assinaturas de blocos que aparecem na margem (topo/pé) de ao menos `minimo` das páginas.

    paginas = [[(texto, y_relativo_inicio, y_relativo_fim), ...], ...]"""
    if len(paginas) < 2:
        return set()
    cont: Counter[str] = Counter()
    for blocos in paginas:
        vistos = {_assinatura(t) for t, y0, y1 in blocos if y1 <= FAIXA_MARGEM or y0 >= 1 - FAIXA_MARGEM}
        cont.update(vistos)
    return {a for a, n in cont.items() if n >= max(2, minimo * len(paginas))}


def limpar_paginas(paginas: list[list[tuple[str, float, float]]]) -> list[list[bool]]:
    """Máscara de blocos mantidos por página (False = cabeçalho, rodapé ou número de página)."""
    repetidos = repetidos_nas_margens(paginas)
    mascara = []
    for blocos in paginas:
        m = []
        for t, y0, y1 in blocos:
            na_margem = y1 <= FAIXA_MARGEM or y0 >= 1 - FAIXA_MARGEM
            m.append(not (na_margem and (_assinatura(t) in repetidos or _NUM_PAGINA.match(t))))
        mascara.append(m)
    return mascara


def ler_pdf(tarefa_id: str, caminho: str) -> DocumentoLido:
    import pymupdf  # import tardio: só o worker tem a dependência

    brutos: list[list[tuple]] = []
    with pymupdf.open(caminho) as doc:
        for pagina in doc:
            altura = pagina.rect.height or 1
            brutos.append([(b[4].strip(), b[1] / altura, b[3] / altura, b) for b in pagina.get_text("blocks") if b[4].strip()])
    mascara = limpar_paginas([[(t, y0, y1) for t, y0, y1, _ in p] for p in brutos])
    paginas = []
    for n, (blocos, manter) in enumerate(zip(brutos, mascara, strict=True), start=1):
        paginas.append(Pagina(numero=n, blocos=[
            Bloco(id=f"p{n}b{i}", texto=desfazer_hifenizacao(t),
                  posicao=Posicao(pagina=n, x0=b[0], y0=b[1], x1=b[2], y1=b[3]))
            for i, ((t, _, _, b), ok) in enumerate(zip(blocos, manter, strict=True)) if ok]))
    tem_texto = any(p.blocos for p in paginas)
    return DocumentoLido(tarefa_id=tarefa_id, origem="nativo", qualidade_leitura=1.0 if tem_texto else 0.0,
                         motivo_baixa_qualidade=None if tem_texto else "PDF sem texto nativo", paginas=paginas)
