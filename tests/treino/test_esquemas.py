import pandas as pd
import pandera.errors as pe
import pytest

from treino.esquemas import conjuntos, validar


@pytest.mark.parametrize("nome", ["pares_ouro_verificador", "perguntas_demo", "intencao", "previsoes", "referencia_deriva"])
def test_arquivos_versionados_seguem_o_esquema(nome):
    validar(nome, conjuntos()[nome]())


def test_lote_com_processo_fora_do_padrao_para_o_pipeline():
    df = pd.DataFrame({"doc_id": [f"d{i}" for i in range(1000)], "processo": ["123"] * 1000, "tipo": ["RO"] * 1000,
                       "texto_integral": ["x" * 300] * 1000})
    with pytest.raises(pe.SchemaErrors):
        validar("repojus", df)


def test_log_de_previsoes_com_texto_do_usuario_e_recusado():
    df = pd.DataFrame({"modelo": ["m"], "versao": ["v"], "tarefa": ["a" * 16], "confianca": [0.5], "abstencao": [False],
                       "texto": ["Meu nome é ..."]})
    with pytest.raises(pe.SchemaErrors):
        validar("previsoes", df)
