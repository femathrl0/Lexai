"""A orquestração não pode divergir do pipeline: confere as DAGs sem instalar o Airflow."""
import ast
import importlib.util
from pathlib import Path

import yaml

from orquestracao import etapas

RAIZ = Path(__file__).resolve().parents[2]
DAGS = RAIZ / "orquestracao" / "dags"


def test_estagios_da_dag_sao_os_do_dvc_yaml_em_ordem_compativel():
    estagios = yaml.safe_load((RAIZ / "dvc.yaml").read_text(encoding="utf-8"))["stages"]
    assert set(etapas.ESTAGIOS_DVC) == set(estagios)
    # nenhum estágio vem antes de um relatório de que ele depende
    produz = {}
    for nome, e in estagios.items():
        for saida in e.get("outs", []) + e.get("metrics", []):
            produz[next(iter(saida)) if isinstance(saida, dict) else saida] = nome
    posicao = {n: i for i, n in enumerate(etapas.ESTAGIOS_DVC)}
    for nome, e in estagios.items():
        for dep in e.get("deps", []):
            if dep in produz:
                assert posicao[produz[dep]] < posicao[nome], f"{nome} roda antes de {produz[dep]}"


def test_comandos_chamam_modulos_que_existem():
    for cmd in (etapas.BAIXAR_LOTE, etapas.DERIVA, etapas.APRENDIZADO_ATIVO, etapas.LIMPAR_ARMAZENAMENTO):
        modulo = cmd.split("-m ", 1)[1].split()[0]
        assert importlib.util.find_spec(modulo) is not None, modulo


def test_toda_dag_tem_id_unico_e_nao_faz_catchup():
    ids = []
    for arq in DAGS.glob("*.py"):
        arvore = ast.parse(arq.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if isinstance(no, ast.Call) and getattr(no.func, "id", "") == "DAG":
                kw = {k.arg: k.value for k in no.keywords}
                ids.append(kw["dag_id"].value)
                assert kw["catchup"].value is False, arq.name
                assert "schedule" in kw and "start_date" in kw, arq.name
    assert len(ids) == len(set(ids)) == 3
