"""Testes de integração com serviços reais (marcador `integracao`): rodam no workflow `integracao.yml` com Postgres
(pgvector) e Redis como services, ou localmente depois de `make up`. Sem os serviços, são pulados."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integracao
RAIZ = Path(__file__).resolve().parents[2]


def _redis():
    redis = pytest.importorskip("redis")
    r = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://127.0.0.1:16379/0"))
    try:
        r.ping()
    except Exception:  # noqa: BLE001
        pytest.skip("Redis fora do ar")
    return r


def test_documento_pela_fila_real_do_rq_ate_o_concluido(tmp_path):
    """Backend enfileira → worker RQ (burst) executa processar_documento → eventos no pub/sub do Redis."""
    r = _redis()
    from rq import SimpleWorker

    from backend.filas import enfileirar_documento
    from contratos.eventos import EVENTO
    from tests.worker.test_fluxo_documento import ACORDAO, _pdf
    from worker.filas import canal_tarefa
    from worker.main import filas

    caminho = _pdf(tmp_path, ACORDAO)
    tarefa = enfileirar_documento(r, "u-integracao", caminho, guardar=False)
    ps = r.pubsub()
    ps.subscribe(canal_tarefa(tarefa))
    ps.get_message(timeout=1)
    os.environ["LEXAI_SEM_LLM"] = "1"  # documento sem a explicação da LLM: só as frases sobre o próprio documento
    SimpleWorker(filas(r), connection=r).work(burst=True)
    eventos = []
    while (m := ps.get_message(timeout=1)) is not None:
        if m["type"] == "message":
            eventos.append(EVENTO.validate_python(json.loads(m["data"])))
    assert eventos and eventos[-1].tipo == "concluido", [e.tipo for e in eventos]
    assert any(e.tipo == "frase" for e in eventos)


def test_migracoes_sobem_e_descem_no_postgres_com_pgvector():
    url = os.getenv("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL não definido")
    env = {**os.environ, "DATABASE_URL": url}
    for cmd in (["upgrade", "head"], ["downgrade", "base"], ["upgrade", "head"]):
        r = subprocess.run([sys.executable, "-m", "alembic", *cmd], cwd=RAIZ, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
    sqlalchemy = pytest.importorskip("sqlalchemy")
    with sqlalchemy.create_engine(url).connect() as c:
        tabelas = {x[0] for x in c.execute(sqlalchemy.text("select tablename from pg_tables where schemaname='public'"))}
        assert {"contas", "tarefas", "resultados", "corpus_juridico", "trechos_usuario"} <= tabelas
        assert c.execute(sqlalchemy.text("select 1 from pg_extension where extname='vector'")).scalar() == 1
