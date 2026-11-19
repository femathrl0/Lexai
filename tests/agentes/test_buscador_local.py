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


def test_adct_recebe_rotulo_proprio(tmp_path):
    cf = "constituicao/constituicao-1988.md"
    base = dict(caminho_relativo=cf, sha256_fonte="f" * 64, status_declarado="in_force")
    def art(n, ident, pos, texto):
        return dict(base, artigo_id=n * 64, identificador_artigo=ident, posicao_inicio=pos, texto_artigo_completo=texto)

    artigos = [art("1", "Art. 1º", 0, "A República."), art("2", "Art. 10", 10, "Colegiados."),
               art("3", "Art. 1º", 90, "Juramento."),
               dict(base, artigo_id="4" * 64, identificador_artigo="Art. 10", posicao_inicio=99,
                    texto_artigo_completo="Fica vedada a dispensa da empregada gestante.")]
    arq = tmp_path / "a.json"
    arq.write_text(json.dumps(artigos), encoding="utf-8")
    b = BuscadorLocal(arq, usar_vetor=False, usar_reranker=False)
    assert [d["fonte"] for d in b.docs] == ["Constituição Federal, Art. 1º", "Constituição Federal, Art. 10",
                                             "ADCT, Art. 1º", "ADCT, Art. 10"]
    assert b.buscar("estabilidade da gestante")[0].fonte == "ADCT, Art. 10"


class _RerankerFake:
    """Nota = 1 se a janela recebida contém "gestante"; súmula com nota média; ementas com nota alta."""

    def predict(self, pares, show_progress_bar=False):
        notas = []
        for _, texto in pares:
            if "Súmula" in texto:
                notas.append(0.6)
            elif "ementa" in texto:
                notas.append(0.9)
            else:
                notas.append(1.0 if "gestante" in texto else 0.1)
        return notas


def test_reranker_le_a_janela_relevante_e_sumula_ganha_vaga(tmp_path):
    longo = "Art. 10.\n" + "\n".join(f"Inciso {n} sobre colegiados e sindicatos rurais." for n in range(60))
    longo += "\nb) da empregada gestante, desde a confirmação da gravidez até cinco meses após o parto."
    artigos = [dict(artigo_id="a" * 64, caminho_relativo="leis/x.md", identificador_artigo="Art. 10",
                    texto_artigo_completo=longo, sha256_fonte="f" * 64, status_declarado="in_force")]
    juris = tmp_path / "j.jsonl"
    linhas = [dict(id=f"e{n}", tipo_fonte="ementa", fonte=f"TRT-10 ementa {n}", texto=f"Ementa gestante estabilidade {n}.")
              for n in range(3)]
    linhas.append(dict(id="s244", tipo_fonte="sumula", fonte="Súmula 244 do TST", texto="Gestante. Estabilidade provisória."))
    juris.write_text("\n".join(json.dumps(x) for x in linhas), encoding="utf-8")
    arq = tmp_path / "a.json"
    arq.write_text(json.dumps(artigos), encoding="utf-8")
    b = BuscadorLocal(arq, jurisprudencia=juris, usar_vetor=False, usar_reranker=False)
    b.reranker = _RerankerFake()
    assert len(longo) > 900 and "gestante" in b._janela_relevante(b.docs[0], "estabilidade da gestante")
    fontes = [t.fonte for t in b.buscar("estabilidade da gestante")]
    assert "Art. 10" in fontes[0]  # a alínea da gestante no fim do artigo foi lida pelo reranker
    assert "Súmula 244 do TST" in fontes and sum("ementa" in f for f in fontes) == 2
