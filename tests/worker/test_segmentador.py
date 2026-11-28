from contratos import Bloco, DocumentoLido, Pagina
from contratos.base import Posicao
from worker.leitura.segmentador import segmentar

P = Posicao(pagina=1, x0=0, y0=0, x1=1, y1=1)


def test_regras_basicas():
    textos = ["RELATÓRIO Fulano ajuizou...", "FUNDAMENTAÇÃO Horas extras...", "ANTE O EXPOSTO, julgo..."]
    doc = DocumentoLido(tarefa_id="t", origem="nativo", qualidade_leitura=1, paginas=[
        Pagina(numero=1, blocos=[Bloco(id=str(i), texto=t, posicao=P) for i, t in enumerate(textos)])])
    assert [t.parte for t in segmentar(doc).trechos] == ["relatorio", "fundamentacao", "dispositivo"]


def _doc(textos):
    return DocumentoLido(tarefa_id="t", origem="nativo", qualidade_leitura=1, paginas=[
        Pagina(numero=1, blocos=[Bloco(id=str(i), texto=t, posicao=P) for i, t in enumerate(textos)])])


def test_acordao_trt():
    textos = ["PODER JUDICIÁRIO", "RECORRENTE : A. B.", "EMENTA\nHORAS EXTRAS: MANTIDA", "RELATÓRIO\nContra a sentença",
              "FUNDAMENTAÇÃO", "Ante o exposto, nego provimento ao tópico.", "CONCLUSÃO", "Nego provimento.",
              "ACÓRDÃO", "ACORDAM os integrantes", "DECLARAÇÃO DE VOTO\nVoto vencido"]
    partes = [t.parte for t in segmentar(_doc(textos)).trechos]
    assert partes == ["outro", "outro", "outro", "relatorio", "fundamentacao", "fundamentacao", "dispositivo",
                      "dispositivo", "dispositivo", "dispositivo", "outro"]


def test_subtitulo_de_merito_depois_da_conclusao_nao_volta():
    textos = ["EMENTA", "RELATÓRIO", "VOTO", "CONCLUSÃO", "MÉRITO: nego provimento"]
    assert [t.parte for t in segmentar(_doc(textos)).trechos][-1] == "dispositivo"
