"""Os três pipelines do worker, um por fila. Esqueleto: só publica status e conclusão.

Cada etapa abaixo tem dono e issue própria; os módulos conversam pelos contratos em contratos/.
"""
import os

from redis import Redis

from contratos import Aviso, Concluido, Status, Versoes

from .publicacao import publicar


def _redis() -> Redis:
    return Redis.from_url(os.getenv("REDIS_URL", "redis://127.0.0.1:16379/0"))


def processar_documento(tarefa_id: str, usuario_id: str, caminho: str, guardar: bool) -> None:
    r = _redis()
    publicar(r, tarefa_id, Status(etapa="lendo"))          # leitura/leitor.py          -> DocumentoLido
    publicar(r, tarefa_id, Status(etapa="classificando"))  # leitura/segmentador.py + modelos/ -> Classificacao
    publicar(r, tarefa_id, Status(etapa="buscando"))       # evidencia/recuperador.py + reranker -> Evidencias
    publicar(r, tarefa_id, Status(etapa="escrevendo"))     # evidencia/explicador.py -> Explicacao
    publicar(r, tarefa_id, Status(etapa="verificando"))    # verificador + guarda de saída -> RespostaVerificada
    publicar(r, tarefa_id, Aviso(categoria="incerteza", texto="Pipeline ainda não implementado (esqueleto)."))
    publicar(r, tarefa_id, Concluido(versoes=Versoes()))
    if not guardar and os.path.exists(caminho):
        os.remove(caminho)  # sem opt-in, o original é descartado (RNF01)


def responder_pergunta(tarefa_id: str, usuario_id: str, pergunta: str, documento_id: str | None) -> None:
    r = _redis()
    publicar(r, tarefa_id, Status(etapa="buscando"))  # guarda de entrada -> recuperador -> reranker
    publicar(r, tarefa_id, Concluido(versoes=Versoes()))


def ingerir_lote(tarefa_id: str, lote: str) -> None:
    """Divisão estrutural -> embeddings -> versão candidata -> regressão -> (Curadoria aprova) publicação."""
    raise NotImplementedError("ver issue de ingestão jurídica (Eng. de dados + Eng. de IA)")
