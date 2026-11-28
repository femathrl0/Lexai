import json

from worker.modelos.registro import FIXADOS, MODELOS, carregar_em_uso, versoes


class Versao:
    def __init__(self, version, tags):
        self.version, self.tags = version, tags


class ClienteFalso:
    def __init__(self, aliases):
        self.aliases = aliases

    def get_model_version_by_alias(self, nome, alias):
        if (nome, alias) not in self.aliases:
            raise RuntimeError("sem alias")
        return self.aliases[(nome, alias)]


def test_sem_mlflow_usa_os_fixados_para_todos_os_modelos():
    m = carregar_em_uso(tracking_uri="")
    assert set(m) == set(MODELOS) and all(x.origem == "fixado" for x in m.values())
    assert m["verificador_nli"].repo == FIXADOS["verificador_nli"]["repo"]
    assert m["verificador_nli"].limiar("sustenta") == 0.55


def test_alias_em_uso_do_mlflow_tem_precedencia_e_herda_limiares():
    cli = ClienteFalso({("verificador_nli", "em-uso"): Versao(7, {"repo": "x/nli", "revisao": "abc123",
                                                                 "limiares": json.dumps({"sustenta": 0.7})})})
    m = carregar_em_uso(cliente=cli)
    nli = m["verificador_nli"]
    assert (nli.origem, nli.versao, nli.repo, nli.uri) == ("mlflow", "7", "x/nli", "models:/verificador_nli@em-uso")
    assert nli.limiar("sustenta") == 0.7 and nli.limiar("sobreposicao_lexical") == 0.2
    assert m["reranker"].origem == "fixado"


def test_fixados_tem_revisao_para_todo_modelo_do_hugging_face():
    assert all(len(c.get("revisao", "")) == 40 for c in FIXADOS.values() if c["tipo"] == "hf")


def test_rotulo_para_versoes():
    v = versoes(carregar_em_uso(tracking_uri=""))
    assert v["reranker"].startswith("BAAI/bge-reranker-v2-m3@") and v["segmentador"].startswith("segmentador@")
