import pytest

from worker.leitura.leitor import desfazer_hifenizacao, limpar_paginas


def test_hifenizacao_de_fim_de_linha():
    assert desfazer_hifenizacao("a presta-\nção de serviço") == "a prestação de serviço"
    assert desfazer_hifenizacao("art. 7º-\nA da lei") == "art. 7º-\nA da lei"


def test_cabecalho_rodape_e_numero_de_pagina_saem():
    pag = lambda n: [("TRIBUNAL REGIONAL DO TRABALHO DA 10ª REGIÃO", 0.02, 0.05),  # noqa: E731
                     (f"Texto do corpo da página {n}", 0.3, 0.6), (f"Página {n} de 3", 0.95, 0.98),
                     (f"Documento assinado em 0{n}/11/2024", 0.9, 0.93)]
    mascara = limpar_paginas([pag(1), pag(2), pag(3)])
    assert mascara == [[False, True, False, False]] * 3


def test_documento_de_uma_pagina_nao_perde_bloco():
    assert limpar_paginas([[("TRIBUNAL", 0.01, 0.04), ("corpo", 0.3, 0.5)]]) == [[True, True]]


def test_ler_pdf_real_com_pymupdf(tmp_path):
    pymupdf = pytest.importorskip("pymupdf")
    from worker.leitura.leitor import ler_pdf

    doc = pymupdf.open()
    for n in range(1, 3):
        p = doc.new_page()
        p.insert_text((72, 30), "PODER JUDICIARIO - CABECALHO")
        p.insert_text((72, 300), f"Conteudo da pagina {n} com presta-")
        p.insert_text((72, 315), "cao de servico.")
        p.insert_text((72, 820), f"{n}")
    arq = tmp_path / "d.pdf"
    doc.save(arq)
    lido = ler_pdf("t", str(arq))
    textos = [b.texto for pg in lido.paginas for b in pg.blocos]
    assert not any("CABECALHO" in t for t in textos) and lido.qualidade_leitura == 1.0
    assert any("prestacao" in t.replace("\n", " ").replace(" ", "") or "presta" in t for t in textos)
