import json

import pytest

from treino.deriva import COLUNAS, REFERENCIA, agregar_por_tarefa, alerta
from worker.modelos import monitoramento


def test_registra_sem_conteudo_do_usuario(tmp_path, monkeypatch):
    monkeypatch.setenv("LEXAI_PREVISOES_DIR", str(tmp_path))
    monitoramento.registrar("classificador_tipo_fase", "v1", 0.9, False, "tarefa-1", "recurso_ordinario", caracteres=100)
    [linha] = monitoramento.ler()
    assert linha["tarefa"] != "tarefa-1" and len(linha["tarefa"]) == 16
    assert set(linha) >= {"modelo", "versao", "confianca", "abstencao", "caracteres"}
    with pytest.raises(ValueError):
        monitoramento.registrar("x", "v", 0.5, False, "t", texto="Meu CPF é ...")


def test_agrega_uma_linha_por_documento():
    log = [{"tarefa": "a", "modelo": "classificador_tipo_fase", "confianca": 0.9, "abstencao": False, "caracteres": 10,
            "qualidade_leitura": 1.0},
           {"tarefa": "a", "modelo": "resultado_pedido", "confianca": 0.0, "abstencao": True},
           {"tarefa": "a", "modelo": "resultado_pedido", "confianca": 0.7, "abstencao": False},
           {"tarefa": "a", "modelo": "extrator_campos", "confianca": 0.5, "abstencao": False, "campos_preenchidos": 4},
           {"tarefa": "b", "modelo": "verificador_nli", "confianca": 0.8, "abstencao": False}]
    [d] = agregar_por_tarefa(log)
    assert d["pedidos"] == 2 and d["fracao_pedidos_sem_resultado"] == 0.5 and d["campos_preenchidos"] == 4
    assert list(d) == COLUNAS


def test_alerta_por_deriva_e_por_abstencao():
    base = {"parcela_colunas_com_deriva": 0.1, "abstencao_referencia": 0.05, "abstencao_atual": 0.06}
    assert alerta(base) == []
    assert alerta({**base, "parcela_colunas_com_deriva": 0.6})
    assert alerta({**base, "abstencao_atual": 0.2})


def test_referencia_versionada_so_tem_numeros():
    cab, *linhas = REFERENCIA.read_text(encoding="utf-8").splitlines()
    assert cab.split(",") == COLUNAS and len(linhas) >= 500
    assert all(float(v) >= 0 for v in linhas[0].split(","))


def test_exemplo_de_previsoes_sem_texto():
    arq = REFERENCIA.with_name("previsoes_exemplo.jsonl")
    for x in map(json.loads, arq.read_text(encoding="utf-8").splitlines()[:200]):
        assert not (monitoramento.CAMPOS_PROIBIDOS & set(x))
