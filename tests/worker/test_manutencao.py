from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from worker.manutencao import limpar, vencidos

AGORA = datetime(2026, 11, 27, 12, tzinfo=UTC)


def obj(nome, horas):
    return SimpleNamespace(object_name=nome, last_modified=AGORA - timedelta(hours=horas))


class S3Falso:
    def __init__(self, buckets):
        self.buckets, self.apagados = buckets, []

    def bucket_exists(self, b):
        return b in self.buckets

    def list_objects(self, b, recursive=True):
        return self.buckets[b]

    def remove_object(self, b, nome):
        self.apagados.append((b, nome))


def test_vencidos():
    assert vencidos([obj("a", 30), obj("b", 2)], AGORA, timedelta(hours=24)) == ["a"]


def test_limpa_entrada_e_prazo_de_guarda(monkeypatch):
    monkeypatch.setenv("PRAZO_GUARDA_DIAS", "30")
    s3 = S3Falso({"entrada": [obj("e1", 25), obj("e2", 1)], "originais": [obj("o1", 24 * 31), obj("o2", 24 * 5)]})
    assert limpar(s3, agora=AGORA) == {"entrada": 1, "originais": 1}
    assert s3.apagados == [("entrada", "e1"), ("originais", "o1")]


def test_simular_nao_apaga():
    s3 = S3Falso({"entrada": [obj("e1", 48)]})
    assert limpar(s3, simular=True, agora=AGORA)["entrada"] == 1 and s3.apagados == []
