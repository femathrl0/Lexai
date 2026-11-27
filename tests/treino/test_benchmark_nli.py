from treino.benchmark_nli import PARES, binario, carregar_pares, escolher_limiar, resumir


def _p(rotulo, p, veredito=None, origem="bateria 17/11"):
    return {"rotulo": rotulo, "p": p, "p_nli": p, "veredito": veredito or ("sustenta" if p >= 0.5 else "nao_trata"),
            "origem": origem}


def test_binario_e_portao():
    pares = [_p("sustenta", 0.9), _p("sustenta", 0.6), _p("contradiz", 0.7), _p("nao_trata", 0.1)]
    m = binario(pares, 0.65)
    assert (m["precisao"], m["recall"], m["liberadas_falsas"]) == (0.5, 0.5, 1)
    escolhido, ok = escolher_limiar(pares)
    assert ok and escolhido["limiar"] == 0.75 and escolhido["precisao"] == 1.0


def test_resumir_conta_contradicao_liberada_e_adversarial():
    pares = [_p("sustenta", 0.9), _p("contradiz", 0.8, "sustenta", origem="adversarial: número trocado")]
    r = resumir(pares, 0.55)
    assert r["contradicoes_liberadas_em_uso"] == 1
    assert r["adversarial"]["n"] == 1


def test_pares_ouro_tem_os_tres_rotulos():
    pares = carregar_pares(PARES)
    assert {p["rotulo"] for p in pares} == {"sustenta", "contradiz", "nao_trata"}
    assert all(p["frase"] and p["trecho"] for p in pares)
