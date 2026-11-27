from treino.segmentador import ajustar_cortes, paragrafos, prever_posicao, rotular_fraco, sem_marcador

ACORDAO = """PODER JUDICIÁRIO
IDENTIFICAÇÃO
RECURSO ORDINÁRIO
RECORRENTE : A. B.
EMENTA
HORAS EXTRAS: SENTENÇA MANTIDA.
RELATÓRIO
Contra a r. sentença recorreu o reclamante.

É o relatório.
FUNDAMENTAÇÃO
ADMISSIBILIDADE
Conheço do recurso.

Ante o exposto, nego provimento ao tópico.
CONCLUSÃO
Nego provimento ao recurso.
ACÓRDÃO
ACORDAM os integrantes da Turma em negar provimento."""


def test_paragrafos_quebram_nos_titulos():
    pars = paragrafos(ACORDAO)
    assert any(p.startswith("EMENTA") for p in pars)
    assert any(p.startswith("CONCLUSÃO") for p in pars)


def test_rotulo_fraco_segue_os_titulos_e_ignora_fecho_de_topico():
    rot = rotular_fraco(paragrafos(ACORDAO))
    partes = {p.split("\n")[0]: y for p, y, _ in rot}
    assert partes["IDENTIFICAÇÃO"] == "outro" and partes["EMENTA"] == "outro"
    assert partes["RELATÓRIO"] == "relatorio"
    assert partes["Ante o exposto, nego provimento ao tópico."] == "fundamentacao"
    assert partes["CONCLUSÃO"] == "dispositivo" and partes["ACÓRDÃO"] == "dispositivo"


def test_documento_sem_relatorio_fica_de_fora():
    assert rotular_fraco(paragrafos("EMENTA\nx\nFUNDAMENTAÇÃO\ny\nCONCLUSÃO\nz")) is None


def test_sem_marcador_tira_so_o_titulo():
    assert sem_marcador("RELATÓRIO\nContra a sentença") == "Contra a sentença"


def test_cortes_de_posicao():
    ex = [(0.05, "outro"), (0.3, "relatorio"), (0.6, "fundamentacao"), (0.95, "dispositivo")]
    cortes = ajustar_cortes(ex)
    assert [prever_posicao(p, cortes) for p, _ in ex] == [y for _, y in ex]
