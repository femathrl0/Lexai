import pytest

from treino.promover import PromocaoInvalida, promover, rollback


class MV:
    def __init__(self, version):
        self.version, self.tags = version, {"estagio": "candidato"}


class Registro:
    def __init__(self, n):
        self.versoes = {str(i): MV(str(i)) for i in range(1, n + 1)}
        self.aliases = {}

    def get_model_version(self, nome, v):
        return self.versoes[str(v)]

    def get_model_version_by_alias(self, nome, alias):
        if alias not in self.aliases:
            raise RuntimeError
        return self.versoes[self.aliases[alias]]

    def set_registered_model_alias(self, nome, alias, v):
        self.aliases[alias] = str(v)

    def delete_registered_model_alias(self, nome, alias):
        self.aliases.pop(alias, None)

    def set_model_version_tag(self, nome, v, k, val):
        self.versoes[str(v)].tags[k] = val


def test_em_uso_exige_aprovado_e_curadoria(tmp_path):
    reg, log = Registro(1), tmp_path / "c.md"
    with pytest.raises(PromocaoInvalida):
        promover(reg, "m", "1", "em-uso", "Felipe", "Laisa", changelog=log)
    promover(reg, "m", "1", "aprovado", "Felipe", changelog=log)
    with pytest.raises(PromocaoInvalida):
        promover(reg, "m", "1", "em-uso", "Felipe", None, changelog=log)
    promover(reg, "m", "1", "em-uso", "Felipe", "Laisa", changelog=log)
    assert reg.aliases["em-uso"] == "1" and reg.versoes["1"].tags["aprovado_por_curadoria"] == "Laisa"


def test_promocao_guarda_anterior_e_rollback_volta(tmp_path):
    reg, log = Registro(2), tmp_path / "c.md"
    for v in ("1", "2"):
        promover(reg, "m", v, "aprovado", "F", changelog=log)
        promover(reg, "m", v, "em-uso", "F", "L", changelog=log)
    assert reg.aliases == {"aprovado": "2", "em-uso": "2", "anterior": "1"}
    assert reg.versoes["1"].tags["estagio"] == "historico"
    rollback(reg, "m", "F", "regressão", changelog=log)
    assert reg.aliases["em-uso"] == "1" and "anterior" not in reg.aliases
    assert log.read_text().count("\n| ") >= 5 and "rollback" in log.read_text()


def test_rollback_sem_anterior_falha(tmp_path):
    with pytest.raises(PromocaoInvalida):
        rollback(Registro(1), "m", "F", "x", changelog=tmp_path / "c.md")
