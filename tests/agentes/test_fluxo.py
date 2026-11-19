from contratos.eventos import Concluido, Frase
from worker.evidencia.agentes.comunicacao import flesch_pt

from .fakes import T477, BuscadorFalso, sistema

BOA = [dict(texto="O empregador paga as verbas rescisórias em até dez dias após o fim do contrato.", trecho="T1"),
       dict(texto="O aviso prévio tem antecedência mínima de trinta dias.", trecho="T2")]
PERGUNTA = "Quais verbas recebo na demissão sem justa causa e em quanto tempo?"


def caminho(estado):
    return [(m.de, m.para, m.tipo) for m in estado.rastro.mensagens if m.tipo != "pedido"]


def test_fluxo_feliz_passa_por_todos_os_agentes_na_ordem():
    eventos = []
    orq, llm, _ = sistema([BOA], eventos=eventos)
    estado = orq.responder(PERGUNTA)
    assert [de for de, _, _ in caminho(estado)] == ["triagem", "pesquisa", "analise", "comunicacao", "validacao"]
    assert [f.trecho_id for f in estado.resposta.frases] == ["lei:477", "lei:487"]
    assert all(f.texto.startswith("Em palavras simples") for f in estado.resposta.frases)
    assert any("não substitui" in a for a in estado.resposta.avisos)
    assert sum(isinstance(e, Frase) for e in eventos) == 2 and isinstance(eventos[-1], Concluido)
    assert estado.resposta.versoes.prompt == "analise/v2"


def test_pedido_fora_do_escopo_nao_chama_a_llm():
    orq, llm, busca = sistema([])
    estado = orq.responder("Como declarar imposto de renda sobre dividendos?")
    assert llm.chamadas == [] and busca.consultas == []
    assert estado.triagem.acao == "fora_escopo" and estado.resposta.frases == []
    assert caminho(estado) == [("triagem", "orquestrador", "resultado")]


def test_caso_concreto_segue_com_encaminhamento():
    orq, llm, _ = sistema([BOA])
    estado = orq.responder("Fui demitido sem justa causa e não recebi as verbas, devo processar a empresa?")
    assert estado.triagem.acao == "orientar_sem_aconselhar"
    assert "situação concreta" in llm.ultimo_usuario["ExplicacaoLLM"]
    assert any("Defensoria" in a for a in estado.resposta.avisos)


def test_dado_pessoal_e_mascarado_antes_dos_agentes():
    orq, llm, busca = sistema([BOA])
    orq.responder("Meu CPF é 123.456.789-09, quanto tempo a empresa tem para pagar a rescisão?")
    assert "123.456" not in busca.consultas[0] and "[CPF]" in busca.consultas[0]


def test_frase_reprovada_volta_para_a_analise_uma_vez_e_e_corrigida():
    ruim = [BOA[0], dict(texto="O prazo para pagar é de vinte dias.", trecho="T1")]
    orq, llm, _ = sistema([ruim, BOA])
    estado = orq.responder(PERGUNTA)
    devolucoes = [m for m in estado.rastro.mensagens if m.tipo == "devolucao"]
    assert len(devolucoes) == 1 and devolucoes[0].para == "analise" and "contradiz" in devolucoes[0].motivo
    assert "REPROVADA" in llm.ultimo_usuario["ExplicacaoLLM"]
    assert len(estado.resposta.frases) == 2 and not any("removidas" in a for a in estado.resposta.avisos)


def test_frase_que_continua_reprovada_e_removida_com_aviso():
    ruim = [BOA[0], dict(texto="Uma regra inventada qualquer.", trecho="T2")]
    orq, llm, _ = sistema([ruim, ruim])
    estado = orq.responder(PERGUNTA)
    assert llm.chamadas.count("ExplicacaoLLM") == 2  # limite: uma reescrita
    assert [f.ordem for f in estado.resposta.frases] == [0]
    assert any("removidas" in a for a in estado.resposta.avisos)


def test_conselho_ao_usuario_e_barrado_mesmo_com_fonte():
    conselho = [dict(texto="Você deve entrar com uma ação imediatamente.", trecho="T1")]
    orq, _, _ = sistema([conselho, conselho], buscador=BuscadorFalso([[T477], [T477]]))
    estado = orq.responder(PERGUNTA)
    assert estado.resposta.frases == []
    assert "aconselhamento" in [m for m in estado.rastro.mensagens if m.tipo == "devolucao"][0].motivo


def test_sem_fonte_pede_nova_busca_com_consulta_reformulada():
    sem = [dict(texto="Não encontrei fonte suficiente.", trecho=None)]
    busca = BuscadorFalso([[], [T477]])
    orq, llm, _ = sistema([sem, sem, [BOA[0]]], buscador=busca)
    estado = orq.responder(PERGUNTA)
    destinos = [m.para for m in estado.rastro.mensagens if m.tipo == "devolucao"]
    assert destinos == ["analise", "pesquisa"]
    assert busca.consultas[1] == "verbas rescisórias art. 477 CLT"
    assert [f.trecho_id for f in estado.resposta.frases] == ["lei:477"]


def test_laços_sao_limitados_e_terminam_com_aviso_de_sem_fonte():
    sem = [dict(texto="Não encontrei fonte suficiente.", trecho=None)]
    orq, llm, _ = sistema([sem, sem, sem], buscador=BuscadorFalso([[], []]))
    estado = orq.responder(PERGUNTA)
    assert estado.novas_buscas == 1 and estado.reescritas == 1
    assert any("fonte jurídica segura" in a for a in estado.resposta.avisos)


def test_comunicacao_nao_muda_o_trecho_e_recupera_frase_perdida():
    orq, _, _ = sistema([BOA], comunicacao=lambda o, t: "" if o == 1 else f"Simples: {t}")
    estado = orq.responder(PERGUNTA)
    assert estado.resposta.frases[1].texto == BOA[1]["texto"]  # perdida → original
    assert [f.trecho_id for f in estado.resposta.frases] == ["lei:477", "lei:487"]


def test_flesch_pt_frases_curtas_sao_mais_faceis():
    assert flesch_pt("O patrão paga em dez dias.") > flesch_pt(
        "A inobservância do disposto no parágrafo sujeitará o infrator à multa administrativa correspondente.")


def test_rastro_e_serializavel_e_tem_tempos():
    orq, _, _ = sistema([BOA])
    estado = orq.responder(PERGUNTA)
    assert all(m.ms is not None for m in estado.rastro.mensagens if m.tipo != "pedido")
    assert estado.model_validate_json(estado.model_dump_json()).resposta == estado.resposta
