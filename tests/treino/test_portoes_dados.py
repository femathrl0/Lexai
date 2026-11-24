"""Portões de dados do Eng. de ML que rodam em todo PR, sem modelos."""

import json
import shutil

from treino.benchmark_rerankers import chave_artigo, metricas_ranking, rrf
from treino.teste_congelado import DIR_LEG, verificar


def test_teste_congelado_de_legislacao_nao_mudou():
    ok, atual, congelado = verificar()
    assert ok, f"conjunto de teste congelado foi alterado: {atual} != {congelado}"


def test_portao_detecta_alteracao_no_teste(tmp_path):
    for nome in ("eval_dataset_test_aprovado.json", "referencias_aprovadas.json", "teste_congelado.json"):
        shutil.copy(DIR_LEG / nome, tmp_path / nome)
    perguntas = json.loads((tmp_path / "eval_dataset_test_aprovado.json").read_text(encoding="utf-8"))
    perguntas[0]["pergunta"] += " (editada)"
    (tmp_path / "eval_dataset_test_aprovado.json").write_text(
        json.dumps(perguntas, ensure_ascii=False), encoding="utf-8"
    )
    assert not verificar(tmp_path)[0]


def test_chave_artigo_normaliza_ordinal_e_espacos():
    assert chave_artigo("clt.md", "Art. 4°") == chave_artigo("clt.md", "Art.  4º")
    assert chave_artigo("clt.md", "Art. 58") != chave_artigo("cc.md", "Art. 58")


def test_rrf_premia_consenso():
    assert rrf([["a", "b", "c"], ["b", "c", "a"]])[0] == "b"


def test_metricas_ranking():
    m = metricas_ranking(["x", "y", "z"], {"y": 2.0})
    assert m["recall@1"] == 0.0 and m["recall@3"] == 1.0 and m["mrr@10"] == 0.5
