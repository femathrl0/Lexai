import json
import re
from pathlib import Path

import pytest

from worker.evidencia import guardas
from worker.ingestao.jurisprudencia.recorte_demo import extrair_ementa, motivo_descarte

RECORTE = Path(__file__).resolve().parents[2] / "corpus" / "jurisprudencia" / "recorte_demo.jsonl"


def _docs():
    return [json.loads(linha) for linha in RECORTE.read_text(encoding="utf-8").splitlines() if linha.strip()]


@pytest.mark.skipif(not RECORTE.exists(), reason="recorte não gerado")
def test_recorte_tem_formato_do_buscador_e_ids_unicos():
    docs = _docs()
    assert len(docs) > 100
    assert len({d["id"] for d in docs}) == len(docs)
    for d in docs:
        assert {"id", "tipo_fonte", "fonte", "texto", "versao"} <= d.keys()
        assert d["tipo_fonte"] in {"sumula", "ementa"} and d["texto"].strip()
    fontes = {d["fonte"] for d in docs}
    assert {"Súmula 244 do TST", "Súmula 462 do TST", "Súmula 441 do TST"} <= fontes  # usadas na bateria


@pytest.mark.skipif(not RECORTE.exists(), reason="recorte não gerado")
def test_recorte_sem_residuo_de_dado_pessoal():
    for d in _docs():
        texto = d["texto"] + " " + d["fonte"]
        for padrao in (guardas.CPF, guardas.CNPJ, guardas.EMAIL, guardas.PROCESSO_CNJ):
            assert not padrao.search(texto), (d["id"], padrao.pattern)
        assert not re.search(r"\b[A-Z]\.\s?[A-Z]\.", d["texto"]) or d["tipo_fonte"] == "sumula", d["id"]


def test_extrai_so_a_ementa_sem_cabecalho():
    teor = ("PODER JUDICIÁRIO\nRECORRENTE: MARIA DA SILVA\nADVOGADO: JOSE SOUZA\nEMENTA\n:\nAVISO PRÉVIO. PROPORCIONALIDADE"
            "\n. O aviso prévio proporcional ao tempo de serviço é devido na forma da lei, conforme a Súmula 441 do TST, "
            "e o recurso não merece provimento quanto ao ponto, mantida a sentença por seus próprios fundamentos.\n"
            "RELATÓRIO\nA reclamante MARIA DA SILVA ajuizou ação...")
    ementa = extrair_ementa(teor)
    assert ementa.startswith("AVISO PRÉVIO. PROPORCIONALIDADE.")
    assert "MARIA" not in ementa and "RELATÓRIO" not in ementa


def test_descarta_ementa_com_nome_ou_empresa():
    vocab = {"o", "recurso", "da", "reclamante", "foi", "provido", "aviso", "previo", "devido"}
    assert motivo_descarte("O recurso da reclamante L. V. H. S. foi provido.", vocab) == "iniciais_de_nome"
    assert motivo_descarte("O recurso da COMERCIAL XYZ LTDA foi provido.", vocab) == "nome_de_empresa"
    assert motivo_descarte("O recurso da reclamante Joana foi provido.", vocab) == "provavel_nome_proprio"
    assert motivo_descarte("Aviso prévio devido.", vocab) is None
