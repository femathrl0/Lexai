from treino.ruido_ocr import queda, ruido


def test_ruido_deterministico_e_proporcional():
    texto = "Conheço do recurso e, no mérito, nego-lhe provimento. " * 20
    assert ruido(texto, 0.0) == texto
    assert ruido(texto, 0.05, semente=1) == ruido(texto, 0.05, semente=1)
    dif = lambda a, b: sum(x != y for x, y in zip(a, b, strict=False)) + abs(len(a) - len(b))  # noqa: E731
    assert dif(texto, ruido(texto, 0.02, 1)) < dif(texto, ruido(texto, 0.10, 1))


def test_queda():
    assert queda(0.95, 0.90) == 0.05
