import pytest
from pydantic import ValidationError

from contratos import (
    Bloco,
    Classificacao,
    Concluido,
    DocumentoLido,
    Erro,
    Evidencias,
    Explicacao,
    Frase,
    FraseAprovada,
    FraseGerada,
    Pagina,
    RespostaVerificada,
    Segmentos,
    Status,
    Trecho,
    TrechoEvidencia,
    Versoes,
)
from contratos.base import Posicao
from contratos.eventos import EVENTO

POS = Posicao(pagina=1, x0=0, y0=0, x1=10, y1=10)


def exemplos():
    doc = DocumentoLido(tarefa_id="t", origem="nativo", qualidade_leitura=0.9,
                        paginas=[Pagina(numero=1, blocos=[Bloco(id="b", texto="ANTE O EXPOSTO", posicao=POS)])])
    seg = Segmentos(tarefa_id="t", metodo="regras",
                    trechos=[Trecho(id="b", parte="dispositivo", texto="x", posicoes=[POS])])
    cls = Classificacao(tarefa_id="t", tipo_documento="sentenca", confianca_tipo=0.9,
                        fase="sentenca", confianca_fase=0.8)
    ev = Evidencias(tarefa_id="t", consulta="q", trechos=[TrechoEvidencia(
        id="clt-477", indice="corpus_juridico", tipo_fonte="lei", texto="Art. 477", fonte="CLT art. 477",
        versao="v1", nota_reranker=0.7)])
    ex = Explicacao(tarefa_id="t", prompt_id="explicador/v1", modelo_llm="qwen3:8b",
                    frases=[FraseGerada(ordem=0, texto="A verba...", trecho_id="clt-477")])
    rv = RespostaVerificada(tarefa_id="t", versoes=Versoes(prompt="explicador/v1"),
                            frases=[FraseAprovada(ordem=0, texto="A verba...", trecho_id="clt-477", fonte="CLT")])
    return [doc, seg, cls, ev, ex, rv]


@pytest.mark.parametrize("obj", exemplos(), ids=lambda o: type(o).__name__)
def test_ida_e_volta_json(obj):
    assert type(obj).model_validate_json(obj.model_dump_json()) == obj


def test_campos_extras_sao_proibidos():
    with pytest.raises(ValidationError):
        Status(etapa="lendo", inesperado=1)


def test_confianca_fora_do_intervalo():
    with pytest.raises(ValidationError):
        Classificacao(tarefa_id="t", tipo_documento=None, confianca_tipo=1.5, fase=None, confianca_fase=0)


@pytest.mark.parametrize("evento", [
    Status(etapa="lendo"),
    Frase(ordem=0, texto="a", trecho_id="x", trecho_texto="y", fonte="CLT"),
    Concluido(versoes=Versoes()),
    Erro(mensagem="m", o_que_fazer="tente de novo"),
])
def test_eventos_discriminados(evento):
    assert EVENTO.validate_json(EVENTO.dump_json(evento)) == evento
