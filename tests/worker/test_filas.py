import fakeredis

from contratos import Status
from worker.filas import ORDEM_PRIORIDADE, PERGUNTAS, canal_tarefa
from worker.main import filas
from worker.publicacao import publicar


def test_perguntas_tem_prioridade():
    assert ORDEM_PRIORIDADE[0] == PERGUNTAS
    assert [q.name for q in filas(fakeredis.FakeRedis())] == list(ORDEM_PRIORIDADE)


def test_publicar_grava_antes_de_publicar():
    r = fakeredis.FakeRedis()
    ps = r.pubsub()
    ps.subscribe(canal_tarefa("t1"))
    ps.get_message()
    gravados = []
    publicar(r, "t1", Status(etapa="lendo"), gravar=lambda t, e: gravados.append((t, e)))
    msg = ps.get_message(timeout=1)
    assert gravados and b'"etapa":"lendo"' in msg["data"]
