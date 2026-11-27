import pytest

from treino.resultado_pedido import avaliar, classificar_regra, trecho_acordam, trecho_conclusao


@pytest.mark.parametrize("texto,esperado", [
    ("conhecer do recurso e, no mérito, negar-lhe provimento", "desprovido"),
    ("Nego provimento ao recurso ordinário.", "desprovido"),
    ("conhecer do recurso e dar-lhe parcial provimento para deferir horas extras", "parcialmente_provido"),
    ("dou provimento parcial ao recurso", "parcialmente_provido"),
    ("conhecer do recurso e dar-lhe provimento para julgar improcedente", "provido"),
    ("Recurso conhecido e desprovido.", "desprovido"),
    ("não conhecer do recurso, por deserto", "nao_conhecido"),
    ("negar provimento ao apelo patronal e dar parcial provimento ao obreiro", None),
    ("aprovar o relatório", None),
])
def test_regra(texto, esperado):
    assert classificar_regra(texto) == esperado


def test_secoes():
    t = ("x\nCONCLUSÃO\nNego provimento.\nÉ o voto.\nACÓRDÃO\nPor tais fundamentos,\n"
         "ACORDAM os integrantes: negar provimento.\nBrasília (DF)")
    assert trecho_conclusao(t) == "Nego provimento."
    assert "negar provimento" in trecho_acordam(t)


def test_troca_grave_conta_so_provido_desprovido():
    m = avaliar(["provido", "desprovido", "parcialmente_provido"], ["desprovido", "provido", "desprovido"])
    assert m["troca_grave"] == 2
