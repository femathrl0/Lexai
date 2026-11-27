from treino.lora_tipo import decidir_promocao


def test_promove_so_com_ganho_e_sem_erro_grave_a_mais():
    base = {"f1_macro": 0.95, "fase_trocada": 10}
    assert decidir_promocao({"f1_macro": 0.975, "fase_trocada": 9}, base)[0]
    assert not decidir_promocao({"f1_macro": 0.965, "fase_trocada": 0}, base)[0]
    ok, motivo = decidir_promocao({"f1_macro": 0.99, "fase_trocada": 11}, base)
    assert not ok and "fase_trocada" in motivo
