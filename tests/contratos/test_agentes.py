"""Testes do contrato do sistema multiagente (contratos/agentes.py) e da categoria `encaminhamento` do Aviso."""
import json

import pytest
from pydantic import ValidationError

from contratos import Aviso, DecisaoTriagem, EstadoTarefa, Evidencias, Mensagem, Rastro, TrechoEvidencia


def _estado():
    e = EstadoTarefa(tarefa_id="t1", pergunta="Meu CPF é 123.456.789-09. Qual o prazo do FGTS?", persona="leigo")
    e.triagem = DecisaoTriagem(acao="responder", pergunta_sanitizada="Meu CPF é [CPF]. Qual o prazo do FGTS?")
    e.evidencias = Evidencias(tarefa_id="t1", consulta="prazo FGTS", trechos=[TrechoEvidencia(
        id="lei:1", indice="corpus_juridico", tipo_fonte="lei", texto="Art. 18", fonte="Lei 8.036/1990, Art. 18",
        versao="v", nota_reranker=0.9)])
    e.frases_para_refazer = {2: "o trecho não trata do que a frase afirma"}
    e.rastro.registrar("orquestrador", "triagem", "pedido", "classificar")
    e.rastro.registrar("validacao", "analise", "devolucao", "refazer", motivo="frase 2: sem apoio", ms=12.5)
    return e


def test_estado_faz_ida_e_volta_em_json():
    e = _estado()
    de_volta = EstadoTarefa.model_validate_json(e.model_dump_json())
    assert de_volta == e
    assert de_volta.frases_para_refazer == {2: "o trecho não trata do que a frase afirma"}  # chave volta a int


def test_rastro_numera_em_ordem_e_valida_tipos():
    r = Rastro()
    assert [r.registrar("orquestrador", a, "pedido", "x").ordem for a in ("triagem", "pesquisa")] == [0, 1]
    with pytest.raises(ValidationError):
        r.registrar("orquestrador", "juiz", "pedido", "agente que não existe")
    with pytest.raises(ValidationError):
        r.registrar("validacao", "analise", "ordem", "tipo que não existe")


def test_mensagem_recusa_campo_extra():
    with pytest.raises(ValidationError):
        Mensagem(ordem=0, de="triagem", para="orquestrador", tipo="resultado", resumo="ok", texto_do_usuario="x")


def test_decisao_triagem_e_imutavel_e_decide_se_segue():
    d = DecisaoTriagem(acao="fora_escopo", pergunta_sanitizada="q", resposta_fixa="Procure…")
    assert not d.segue_para_busca
    assert DecisaoTriagem(acao="orientar_sem_aconselhar", pergunta_sanitizada="q").segue_para_busca
    with pytest.raises(ValidationError):
        d.acao = "responder"


def test_registro_nao_guarda_a_pergunta_crua():
    registro = _estado().para_registro()
    assert "pergunta" not in registro
    assert "123.456.789-09" not in json.dumps(registro, ensure_ascii=False)
    assert registro["triagem"]["pergunta_sanitizada"].startswith("Meu CPF é [CPF]")


def test_aviso_aceita_encaminhamento():
    assert Aviso(categoria="encaminhamento", texto="Procure a Defensoria.").categoria == "encaminhamento"
    with pytest.raises(ValidationError):
        Aviso(categoria="conselho", texto="x")
