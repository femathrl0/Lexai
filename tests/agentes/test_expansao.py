from contratos.agentes import DecisaoTriagem, EstadoTarefa
from worker.evidencia.agentes.buscadores import _numeros_artigo
from worker.evidencia.agentes.expansao import expandir
from worker.evidencia.agentes.pesquisa import AgentePesquisa


def test_expansao_traz_vocabulario_do_art_477():
    consulta, termos = expandir("Quais verbas recebo na demissão sem justa causa e em quanto tempo?")
    assert consulta.startswith("Quais verbas recebo")  # nunca remove o que a pessoa escreveu
    for t in ("extinção", "rescisórias", "prazo"):
        assert t in termos


def test_expansao_da_gestante_e_sem_regra_nao_muda():
    assert "estabilidade" in expandir("Fui demitida grávida, devo processar a empresa?")[1]
    assert expandir("Que exigência o art. 60 da CLT estabelece?") == ("Que exigência o art. 60 da CLT estabelece?", [])


def test_numeros_de_artigo_na_pergunta():
    assert _numeros_artigo("Como os arts. 457 e 458 da CLT descrevem") == {"457", "458"}
    assert _numeros_artigo("o art. 391-A da CLT") == {"391-A"}
    assert _numeros_artigo("artigo 60") == {"60"}
    assert _numeros_artigo("Quais verbas recebo?") == set()


class _Buscador:
    versao = "fake"

    def __init__(self):
        self.consultas = []

    def buscar(self, consulta, por_fonte=3):
        self.consultas.append(consulta)
        return []


def test_pesquisa_expande_so_na_primeira_busca():
    b = _Buscador()
    estado = EstadoTarefa(tarefa_id="t", pergunta="q")
    estado.triagem = DecisaoTriagem(acao="responder", pergunta_sanitizada="Quanto tempo de aviso na demissão?")
    estado.consulta = estado.triagem.pergunta_sanitizada
    saida = AgentePesquisa(b).executar(estado)
    assert "prévio proporcional" in b.consultas[0] and saida.dados["termos_acrescentados"]
    AgentePesquisa(b).executar(estado)  # 2ª passada = nova busca pedida pela Validação: reformula, não expande de novo
    assert b.consultas[1].endswith("CLT direito do trabalho")
