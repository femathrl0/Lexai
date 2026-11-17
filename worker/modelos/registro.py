"""Carregamento dos modelos "em uso" no MLflow (Eng. de ML e MLOps).

Estágios: candidato -> aprovado -> em uso. Só Eng. de ML + Curadoria promovem para "em uso".
"""
MODELOS = (
    "classificador_tipo_fase",
    "extrator_campos",
    "resultado_pedido",
    "intencao_guarda",
    "reranker",
    "verificador_nli",
)


def carregar_em_uso() -> dict:
    raise NotImplementedError("TODO: buscar no MLflow a versão com alias 'em-uso' de cada modelo em MODELOS")
