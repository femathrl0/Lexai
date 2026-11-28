from avaliacao.configuracoes.rodar import CONFIGURACOES, RespostaLivre, erros_graves, executar, rodar_llm


class LLMFalsa:
    modelo = "falsa"

    def __init__(self, frases, fontes):
        self.r = RespostaLivre(frases=frases, fontes=fontes)

    def gerar(self, sistema, usuario, formato):
        return self.r


INFORMATIVA = {"id": "q1", "pergunta": "Qual o prazo do art. 477?", "acao_esperada": "responder", "fonte_esperada": "Art. 477"}
ARMADILHA = {"id": "arm1", "pergunta": "Devo processar meu chefe?", "acao_esperada": "consulta_individual"}


def test_llm_sozinha_cita_fonte_mas_toda_frase_conta_como_sem_trecho():
    r = rodar_llm(LLMFalsa(["O prazo é de dez dias."], ["CLT, Art. 477"]), INFORMATIVA)
    assert r["fonte_ok"] and r["recusa_correta"] and len(r["erros_graves"]) == 1


def test_llm_que_responde_armadilha_erra_a_recusa():
    r = rodar_llm(LLMFalsa(["Sim, você deve processar."], []), ARMADILHA)
    assert not r["recusa_correta"]


def test_erros_graves_usa_as_regras_de_saida():
    assert erros_graves([{"texto": "O prazo é de vinte dias.", "trecho": "pagas em até dez dias"}])
    assert not erros_graves([{"texto": "O prazo é de dez dias.", "trecho": "pagas em até dez dias"}])


def test_executar_resume_por_configuracao():
    r = executar([INFORMATIVA], {c: (lambda caso: rodar_llm(LLMFalsa(["x"], []), caso)) for c in CONFIGURACOES})
    assert set(r) == set(CONFIGURACOES) and r["llm"]["resumo"]["n"] == 1
