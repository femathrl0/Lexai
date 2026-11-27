from treino.aprendizado_ativo import config_xml, incerta, limiares_em_uso, para_label_studio, selecionar


def _p(modelo, tarefa, conf, abst=False, previsao=None):
    return {"modelo": modelo, "tarefa": tarefa, "confianca": conf, "abstencao": abst, "previsao": previsao, "versao": "v1"}


def test_limiares_vem_do_em_uso():
    lim = limiares_em_uso()
    assert lim["verificador_nli"] == 0.55 and lim["classificador_tipo_fase"] == 0.44


def test_seleciona_incertas_com_rodizio_e_uma_por_documento():
    log = [_p("classificador_tipo_fase", "a", 0.9), _p("classificador_tipo_fase", "b", 0.1),
           _p("classificador_tipo_fase", "b", 0.05), _p("resultado_pedido", "c", 0.0, abst=True),
           _p("verificador_nli", "d", 0.3, previsao="reprovada"), _p("verificador_nli", "e", 0.2)]
    lim = {"classificador_tipo_fase": 0.44, "resultado_pedido": 0.5, "verificador_nli": 0.55}
    lote = selecionar(log, lim, 3)
    assert len(lote) == 3 and len({p["modelo"] for p in lote}) == 3
    assert not incerta(log[0], lim)
    assert [p["confianca"] for p in lote if p["modelo"] == "classificador_tipo_fase"] == [0.05]


def test_formato_label_studio_sem_texto():
    [t] = para_label_studio([_p("resultado_pedido", "c", 0.0, abst=True, previsao="nao_identificado")])
    assert t["data"]["tarefa"] == "c" and t["meta"]["motivo"] == "abstencao"
    assert t["predictions"][0]["result"][0]["value"]["choices"] == ["nao_identificado"]
    assert "texto" not in t["data"]
    assert '<Choice value="procedente"/>' in config_xml("resultado_pedido")
