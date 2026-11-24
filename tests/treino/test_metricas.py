import math

import pytest

from treino.metricas import ece, f1_por_classe, limiar_abstencao, ndcg_at_k, recall_at_k, reciprocal_rank


def test_ndcg_perfeito_e_invertido():
    assert ndcg_at_k([2, 1, 0], [2, 1], 3) == pytest.approx(1.0)
    pior = ndcg_at_k([0, 1, 2], [2, 1], 3)
    assert 0 < pior < 1


def test_ndcg_relevancia_graduada_conta_mais():
    # relevante 2 na 1ª posição vale mais que relevante 1 na 1ª posição
    assert ndcg_at_k([2, 1], [2, 1], 2) > ndcg_at_k([1, 2], [2, 1], 2)


def test_ndcg_sem_relevante_e_zero():
    assert ndcg_at_k([0, 0], [], 2) == 0.0


def test_ndcg_valor_conhecido():
    # um relevante (2) na posição 2: dcg = 3/log2(3); ideal = 3/log2(2)
    assert ndcg_at_k([0, 2], [2], 5) == pytest.approx((3 / math.log2(3)) / 3)


def test_recall_e_mrr():
    assert recall_at_k([0, 2, 0, 1], 2, 2) == 0.5
    assert recall_at_k([0, 2, 0, 1], 2, 4) == 1.0
    assert reciprocal_rank([0, 0, 1]) == pytest.approx(1 / 3)
    assert reciprocal_rank([0, 0, 1], k=2) == 0.0


def test_f1_por_classe():
    r = f1_por_classe(["a", "a", "b", "b"], ["a", "b", "b", "b"], ["a", "b"])
    assert r["a"]["precisao"] == 1.0 and r["a"]["recall"] == 0.5
    assert r["b"]["f1"] == pytest.approx(0.8)


def test_ece_calibrado_e_descalibrado():
    assert ece([0.9] * 10, [True] * 9 + [False]) == pytest.approx(0.0, abs=1e-9)
    assert ece([0.99] * 10, [True] * 5 + [False] * 5) == pytest.approx(0.49)


def test_limiar_abstencao_atinge_alvo():
    conf = [0.99, 0.95, 0.9, 0.6, 0.55, 0.5]
    acertos = [True, True, True, False, True, False]
    limiar, acc, cob = limiar_abstencao(conf, acertos, 1.0)
    assert limiar == 0.9 and acc == 1.0 and cob == 0.5


def test_limiar_abstencao_empates_entram_juntos():
    limiar, acc, cob = limiar_abstencao([0.9, 0.9, 0.5], [True, False, True], 0.6)
    assert (limiar, cob) == (0.5, 1.0)  # 0.9 isolado tem 50% < 60%; incluir os empates não "corta" no meio
