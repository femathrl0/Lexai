import json
import logging

from comum.log import FormatadorJSON, mascarar


def test_mascara_dado_pessoal():
    t = mascarar("CPF 123.456.789-09, e-mail fulano@x.com.br, tel (61) 99876-5432")
    assert "123.456" not in t and "fulano" not in t and "99876" not in t


def test_linha_json_com_campos_extras_mascarados():
    r = logging.LogRecord("worker", logging.INFO, "", 0, "tarefa %s", ("t1",), None)
    r.etapa, r.obs = "lendo", "cpf 12345678909"
    linha = json.loads(FormatadorJSON("worker").format(r))
    assert linha["msg"] == "tarefa t1" and linha["servico"] == "worker" and linha["etapa"] == "lendo"
    assert linha["obs"] == "cpf [CPF]"
