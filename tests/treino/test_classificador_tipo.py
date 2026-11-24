from collections import Counter

from treino.classificador_tipo import (
    CLASSES,
    FASE_DO_TIPO,
    MAPA_CLASSE,
    avaliar,
    corrigir_rotulo,
    divisao,
    regra_cabecalho,
    rotular,
    sem_cabecalho,
)

CABECALHO_RO = """PODER JUDICIÁRIO
JUSTIÇA DO TRABALHO
TRIBUNAL REGIONAL DO TRABALHO DA 10ª REGIÃO
IDENTIFICAÇÃO
PROCESSO nº 0000331-08.2024.5.10.0011 - RECURSO ORDINÁRIO - RITO SUMARÍSSIMO (11886)
RELATOR: JUIZ CONVOCADO FULANO
RECORRENTE: R. M. C.
RECORRIDO: C. L. S. P.
EMENTA
DIREITO DO TRABALHO. RECURSO ORDINÁRIO. HORAS EXTRAS. PARCIAL PROVIMENTO.
O recorrente pede a reforma da sentença quanto às horas extras."""

CABECALHO_ED_COM_CLASSE_DO_RO = """PODER JUDICIÁRIO
IDENTIFICAÇÃO
PROCESSO n.º 0000400-23.2022.5.10.0007 - RECURSO ORDINÁRIO TRABALHISTA (1009)
EMBARGANTE: C. L. P. S.
EMBARGADO: W. J. L.
EMENTA
EMBARGOS DECLARATÓRIOS. OMISSÃO. INEXISTÊNCIA."""


def test_mapa_cobre_so_classes_conhecidas():
    assert {tipo for tipo, _ in MAPA_CLASSE.values()} == set(CLASSES)
    assert set(FASE_DO_TIPO) <= set(CLASSES)


def test_rotular():
    assert rotular("Agravo de Petição") == ("agravo_peticao", "execucao")
    assert rotular("Recurso Ordinário - Rito Sumaríssimo") == ("recurso_ordinario", "conhecimento")
    assert rotular("acordao") is None  # rótulo genérico: descartado, não adivinhado


def test_divisao_por_processo_estavel_e_ignora_formatacao():
    assert divisao("0000331-08.2024.5.10.0011") == divisao("00003310820245100011")
    assert divisao("0000331-08.2024.5.10.0011") == divisao("0000331-08.2024.5.10.0011")


def test_divisao_proporcoes_aproximadas():
    c = Counter(divisao(f"{i:07d}-00.2024.5.10.0001") for i in range(5000))
    assert 0.66 < c["treino"] / 5000 < 0.74
    assert 0.12 < c["validacao"] / 5000 < 0.18
    assert 0.12 < c["teste"] / 5000 < 0.18


def test_sem_cabecalho_remove_identificacao_e_mascara_classe():
    t = sem_cabecalho(CABECALHO_RO)
    assert "PROCESSO" not in t and "RELATOR" not in t
    assert "RECURSO ORDINÁRIO" not in t.upper() and "RECORRENTE" not in t.upper()
    assert "HORAS EXTRAS" in t  # conteúdo fica


def test_regra_cabecalho():
    assert regra_cabecalho(CABECALHO_RO) == "recurso_ordinario"
    assert (
        regra_cabecalho("PROCESSO 0000714-38.2023.5.10.0005 AP - ACÓRDÃO\nAGRAVANTE: X\nEMENTA\n...")
        == "agravo_peticao"
    )
    assert regra_cabecalho("texto sem cabeçalho nenhum") is None


def test_embargante_vence_classe_do_recurso_embargado():
    assert regra_cabecalho(CABECALHO_ED_COM_CLASSE_DO_RO) == "embargos_declaracao"
    assert corrigir_rotulo("recurso_ordinario", CABECALHO_ED_COM_CLASSE_DO_RO) == ("embargos_declaracao", True)
    assert corrigir_rotulo("recurso_ordinario", CABECALHO_RO) == ("recurso_ordinario", False)


def test_avaliar_conta_troca_de_fase_e_abstencao():
    y = ["recurso_ordinario", "agravo_peticao", "agravo_instrumento"]
    p = ["agravo_peticao", "agravo_peticao", None]
    m = avaliar(y, p, fase_true=["conhecimento", "execucao", "execucao"])
    assert m["fase_trocada"] == 1  # conhecimento lido como execução: o erro que importa
    assert m["fase_abstencao"] == 1
    assert m["abstencoes"] == 1
