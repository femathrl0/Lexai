"""Leitor (Eng. de dados): PDF nativo -> DocumentoLido, guardando página e posição de cada bloco.

Semana 1–4: só PDF com texto nativo (PyMuPDF). Semana 5: foto -> checagem de qualidade -> PaddleOCR.
"""
from contratos import Bloco, DocumentoLido, Pagina
from contratos.base import Posicao


def ler_pdf(tarefa_id: str, caminho: str) -> DocumentoLido:
    import pymupdf  # import tardio: só o worker tem a dependência

    paginas = []
    with pymupdf.open(caminho) as doc:
        for n, pagina in enumerate(doc, start=1):
            blocos = [
                Bloco(id=f"p{n}b{i}", texto=b[4].strip(), posicao=Posicao(pagina=n, x0=b[0], y0=b[1], x1=b[2], y1=b[3]))
                for i, b in enumerate(pagina.get_text("blocks"))
                if b[4].strip()
            ]
            paginas.append(Pagina(numero=n, blocos=blocos))
    tem_texto = any(p.blocos for p in paginas)
    # TODO: remover cabeçalho, rodapé e hifenização; PDF sem texto nativo vai para o OCR.
    return DocumentoLido(
        tarefa_id=tarefa_id,
        origem="nativo",
        qualidade_leitura=1.0 if tem_texto else 0.0,
        motivo_baixa_qualidade=None if tem_texto else "PDF sem texto nativo",
        paginas=paginas,
    )
