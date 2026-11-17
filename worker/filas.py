"""Nomes das filas e canais. Ordem = prioridade: perguntas não esperam atrás de documentos longos."""
PERGUNTAS = "perguntas"
DOCUMENTOS = "documentos"
INGESTAO_JURIDICA = "ingestao_juridica"

ORDEM_PRIORIDADE = (PERGUNTAS, DOCUMENTOS, INGESTAO_JURIDICA)
MAX_TENTATIVAS = 2


def canal_tarefa(tarefa_id: str) -> str:
    return f"tarefa:{tarefa_id}"
