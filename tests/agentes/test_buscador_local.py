import json

from worker.evidencia.agentes.buscadores import BuscadorLocal


def test_bm25_acha_artigo_por_numero_e_por_tema(tmp_path):
    artigos = [
        dict(artigo_id="a" * 64, caminho_relativo="codigos/consolidacao-das-leis-do-trabalho-clt-del-5452-1943.md",
             identificador_artigo="Art. 477", texto_artigo_completo="##### Art. 477.\n\nPagamento das verbas rescisórias.",
             sha256_fonte="f" * 64, status_declarado="in_force"),
        dict(artigo_id="b" * 64, caminho_relativo="codigos/consolidacao-das-leis-do-trabalho-clt-del-5452-1943.md",
             identificador_artigo="Art. 129", texto_artigo_completo="Todo empregado terá direito anualmente ao gozo de férias.",
             sha256_fonte="f" * 64, status_declarado="in_force"),
        dict(artigo_id="c" * 64, caminho_relativo="codigos/codigo-civil-lei-10406-2002.md", identificador_artigo="Art. 1",
             texto_artigo_completo="Revogado.", sha256_fonte="f" * 64, status_declarado="revoked"),
    ]
    juris = tmp_path / "j.jsonl"
    juris.write_text(json.dumps(dict(id="s1", tipo_fonte="sumula", fonte="Súmula 171 do TST",
                                     texto="Férias proporcionais na extinção do contrato.")) + "\n", encoding="utf-8")
    arq = tmp_path / "a.json"
    arq.write_text(json.dumps(artigos), encoding="utf-8")
    b = BuscadorLocal(arq, jurisprudencia=juris, usar_vetor=False, usar_reranker=False)
    assert len(b.docs) == 3  # o revogado sai da busca
    assert b.buscar("o que diz o art. 477?")[0].fonte == "CLT, Art. 477"
    ferias = b.buscar("direito a férias", por_fonte=1)
    assert {t.tipo_fonte for t in ferias} == {"lei", "sumula"}  # um de cada tipo no topo
