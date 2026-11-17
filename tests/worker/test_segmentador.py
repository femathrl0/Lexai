from contratos import Bloco, DocumentoLido, Pagina
from contratos.base import Posicao
from worker.leitura.segmentador import segmentar

P = Posicao(pagina=1, x0=0, y0=0, x1=1, y1=1)


def test_regras_basicas():
    textos = ["RELATÓRIO Fulano ajuizou...", "FUNDAMENTAÇÃO Horas extras...", "ANTE O EXPOSTO, julgo..."]
    doc = DocumentoLido(tarefa_id="t", origem="nativo", qualidade_leitura=1, paginas=[
        Pagina(numero=1, blocos=[Bloco(id=str(i), texto=t, posicao=P) for i, t in enumerate(textos)])])
    assert [t.parte for t in segmentar(doc).trechos] == ["relatorio", "fundamentacao", "dispositivo"]
