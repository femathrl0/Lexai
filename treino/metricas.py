"""Métricas do cargo em Python puro (rodam no CI sem bibliotecas de ML).

- Ranking (reranker): nDCG@k com relevância graduada 0–2, recall@k, MRR.
- Classificação: F1 por classe, calibração (ECE) e escolha do limiar de abstenção (RNF04).
"""

from __future__ import annotations

import math
from collections.abc import Sequence


def dcg(relevancias: Sequence[float], k: int) -> float:
    return sum((2**r - 1) / math.log2(i + 2) for i, r in enumerate(relevancias[:k]))


def ndcg_at_k(relevancias_ordenadas: Sequence[float], todas_relevancias: Sequence[float], k: int) -> float:
    """nDCG@k. `relevancias_ordenadas` = relevância de cada item na ordem do ranking avaliado;
    `todas_relevancias` = relevâncias de todos os itens relevantes conhecidos (ideal)."""
    ideal = dcg(sorted(todas_relevancias, reverse=True), k)
    return dcg(relevancias_ordenadas, k) / ideal if ideal > 0 else 0.0


def recall_at_k(relevancias_ordenadas: Sequence[float], n_relevantes: int, k: int) -> float:
    if n_relevantes == 0:
        return 0.0
    return sum(1 for r in relevancias_ordenadas[:k] if r > 0) / n_relevantes


def reciprocal_rank(relevancias_ordenadas: Sequence[float], k: int | None = None) -> float:
    for i, r in enumerate(relevancias_ordenadas[:k] if k else relevancias_ordenadas):
        if r > 0:
            return 1.0 / (i + 1)
    return 0.0


def f1_por_classe(y_true: Sequence[str], y_pred: Sequence[str], classes: Sequence[str]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for c in classes:
        tp = sum(1 for t, p in zip(y_true, y_pred, strict=True) if t == c and p == c)
        fp = sum(1 for t, p in zip(y_true, y_pred, strict=True) if t != c and p == c)
        fn = sum(1 for t, p in zip(y_true, y_pred, strict=True) if t == c and p != c)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        out[c] = {"precisao": prec, "recall": rec, "f1": f1, "suporte": tp + fn}
    return out


def ece(confiancas: Sequence[float], acertos: Sequence[bool], n_faixas: int = 10) -> float:
    """Expected Calibration Error: média ponderada de |acurácia − confiança| por faixa de confiança."""
    n = len(confiancas)
    if n == 0:
        return 0.0
    total = 0.0
    for b in range(n_faixas):
        lo, hi = b / n_faixas, (b + 1) / n_faixas
        idx = [i for i, c in enumerate(confiancas) if (lo < c <= hi) or (b == 0 and c == 0)]
        if idx:
            acc = sum(acertos[i] for i in idx) / len(idx)
            conf = sum(confiancas[i] for i in idx) / len(idx)
            total += len(idx) / n * abs(acc - conf)
    return total


def limiar_abstencao(
    confiancas: Sequence[float], acertos: Sequence[bool], precisao_alvo: float
) -> tuple[float, float, float]:
    """Menor limiar t tal que a acurácia nas previsões com confiança >= t atinge `precisao_alvo`.

    Devolve (limiar, acurácia_aceitas, cobertura). Se nenhum limiar atinge o alvo, devolve o que maximiza a
    acurácia com cobertura >= 1% (o app então se abstém quase sempre — sinal de modelo insuficiente).
    """
    pares = sorted(zip(confiancas, acertos, strict=True), key=lambda x: -x[0])
    n = len(pares)
    melhor = (1.0, 0.0, 0.0)
    acertos_acum = 0
    candidatos: list[tuple[float, float, float]] = []
    for i, (c, a) in enumerate(pares, start=1):
        acertos_acum += a
        # só avalia no último item de cada valor de confiança (empates entram juntos)
        if i < n and pares[i][0] == c:
            continue
        candidatos.append((c, acertos_acum / i, i / n))
    validos = [x for x in candidatos if x[1] >= precisao_alvo]
    if validos:
        return min(validos, key=lambda x: x[0])
    com_cobertura = [x for x in candidatos if x[2] >= 0.01]
    return max(com_cobertura, key=lambda x: x[1]) if com_cobertura else melhor
