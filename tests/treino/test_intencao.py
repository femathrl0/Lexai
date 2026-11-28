from treino.intencao import ACOES, ARQUIVO, avaliar, divisao_por_molde, gerar_casos


def test_rascunho_versionado_e_reproduzivel():
    casos = gerar_casos()
    assert {c["acao_esperada"] for c in casos} == set(ACOES)
    assert ARQUIVO.read_text(encoding="utf-8").count("\n") == len(casos)
    assert all("aguarda aceite" in c["status"] for c in casos)


def test_divisao_por_molde_nao_mistura():
    casos = gerar_casos()
    por_molde = {}
    for c in casos:
        por_molde.setdefault(c["molde"], set()).add(divisao_por_molde(c["molde"]))
    assert all(len(v) == 1 for v in por_molde.values())


def test_erro_grave_caso_concreto_tratado_como_informativo():
    m = avaliar(["orientar_sem_aconselhar", "responder"], ["responder", "responder"])
    assert m["erros_graves"] == 1
