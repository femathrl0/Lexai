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


def test_documento_que_nao_e_pdf_nem_foto_e_recusado():
    r = cliente.post("/tarefas/documentos", files={"arquivo": ("x.pdf", b"MZ\x90\x00 executavel", "application/pdf")})
    assert r.status_code == 415


def test_documento_grande_demais_e_recusado(monkeypatch):
    from backend import armazenamento

    monkeypatch.setattr(armazenamento.config, "upload_max_mb", 0)
    r = cliente.post("/tarefas/documentos", files={"arquivo": ("s.pdf", b"%PDF-1.4 " + b"x" * 2048, "application/pdf")})
    assert r.status_code == 413


def test_ready_com_redis_no_ar():
    r = cliente.get("/ready")
    assert r.status_code == 200 and r.json()["redis"] == "ok"


def test_job_timeout_maior_que_uma_pergunta():
    r = cliente.post("/tarefas/perguntas", json={"pergunta": "O que é FGTS?"})
    assert Queue(PERGUNTAS, connection=redis).fetch_job(r.json()["tarefa_id"]).timeout >= 300


def test_producao_recusa_segredo_de_exemplo():
    import pytest

    from backend.config import Config

    with pytest.raises(ValueError):
        Config(lexai_ambiente="producao", segredo_sessao="troque-este-segredo", minio_root_password="x")
