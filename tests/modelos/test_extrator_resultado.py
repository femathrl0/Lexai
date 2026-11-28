from tests.worker.test_fluxo_documento import ACORDAO
from worker.modelos.extrator_campos import como_dict, extrair, numero_processo, pedidos
from worker.modelos.resultado_pedido import classificar_regra, pedidos_da_ementa, resultado_do_topico
from worker.modelos.tipo_documento import classificar


def test_campos_do_acordao_sem_nome_de_parte():
    c = como_dict(extrair(ACORDAO))
    assert c["numero_processo"] == "0000566-05.2024.5.10.0001"
    assert c["relator"].startswith("PEDRO LUIS")
    assert c["papeis_partes"] == "recorrente, recorrido"
    assert "M. V. M." not in " ".join(v for v in c.values() if v)


def test_numero_cnj_normalizado():
    assert numero_processo("PROCESSO 00005660520245100001") == "0000566-05.2024.5.10.0001"


def test_campo_ausente_e_nao_identificado():
    c = {x.nome: x for x in extrair("texto sem nada")}
    assert c["numero_processo"].valor is None and c["numero_processo"].confianca == 0.0


def test_pedidos_da_ementa():
    ementa = "HORAS EXTRAS. CONTROLES DE JORNADA. HORAS EXTRAS DEVIDAS.\nDANO MORAL. NAO CONFIGURADO.\n"
    assert pedidos("EMENTA\n" + ementa + "RELATÓRIO")[:1] == ["HORAS EXTRAS"]
    res = {p.pedido: p.resultado for p in pedidos_da_ementa(ementa)}
    assert res["DANO MORAL"] == "improcedente"


def test_topico_sem_resultado_do_direito_nao_adivinha():
    assert resultado_do_topico("SENTENÇA MANTIDA.") == ("nao_identificado", 0.0)
    assert resultado_do_topico("HORAS EXTRAS INDEVIDAS.")[0] == "improcedente"
    assert resultado_do_topico("PARCIALMENTE DEVIDAS.")[0] == "parcialmente_procedente"


def test_tipo_por_regras_e_abstencao_sem_cabecalho():
    assert classificar(ACORDAO)["tipo"] == "recurso_ordinario"
    sem = classificar("Texto colado sem cabeçalho nenhum.")
    assert sem["abstencao"] and sem["tipo"] is None and sem["fase"] is None


def test_regra_do_recurso_no_worker():
    assert classificar_regra("nego-lhe provimento") == "desprovido"
