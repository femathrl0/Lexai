import fakeredis
from fastapi.testclient import TestClient
from rq import Queue

from backend.main import app, get_redis
from worker.filas import DOCUMENTOS, PERGUNTAS

redis = fakeredis.FakeRedis()
app.dependency_overrides[get_redis] = lambda: redis
cliente = TestClient(app)


def test_health():
    assert cliente.get("/health").json() == {"status": "ok"}


def test_pergunta_vai_para_fila_prioritaria():
    r = cliente.post("/tarefas/perguntas", json={"pergunta": "O que é aviso prévio?"})
    assert r.status_code == 200 and "não substitui advogado" in r.json()["aviso"]
    assert Queue(PERGUNTAS, connection=redis).fetch_job(r.json()["tarefa_id"]) is not None


def test_documento_vai_para_fila_documentos():
    r = cliente.post("/tarefas/documentos", files={"arquivo": ("s.pdf", b"%PDF-1.4", "application/pdf")})
    job = Queue(DOCUMENTOS, connection=redis).fetch_job(r.json()["tarefa_id"])
    assert job is not None and job.kwargs["guardar"] is False
    assert job.retries_left == 1  # no máximo duas tentativas
