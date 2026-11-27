import json

from treino.portao_regressao import LINHA_BASE, comparar, extrair, verificar

REF = {"metricas": {"f1_macro": {"valor": 0.90, "direcao": "maior", "tolerancia": 0.01},
                    "ece": {"valor": 0.05, "direcao": "menor", "tolerancia": 0.0}},
       "erros_graves": {"troca": 2}}


def test_passa_quando_igual_ou_melhor():
    assert comparar("m", REF, {"f1_macro": 0.895, "ece": 0.04, "troca": 2}) == []


def test_reprova_metrica_pior_alem_da_tolerancia():
    falhas = comparar("m", REF, {"f1_macro": 0.88, "ece": 0.04, "troca": 0})
    assert len(falhas) == 1 and "f1_macro" in falhas[0]


def test_reprova_metrica_menor_e_melhor():
    assert any("ece" in f for f in comparar("m", REF, {"f1_macro": 0.95, "ece": 0.06, "troca": 0}))


def test_erro_grave_nao_tem_tolerancia():
    assert any("troca" in f for f in comparar("m", REF, {"f1_macro": 0.99, "ece": 0.0, "troca": 3}))


def test_metrica_ausente_reprova():
    assert any("ausente" in f for f in comparar("m", REF, {"ece": 0.0, "troca": 0}))


def test_extrair_aceita_chaves_com_barra_e_dois_pontos():
    rel = {"resultados": {"reranker:BAAI/bge-reranker-v2-m3": {"metricas": {"test": {"ndcg@5": 0.9}}}}}
    assert extrair(rel, "resultados.reranker:BAAI/bge-reranker-v2-m3.metricas.test") == {"ndcg@5": 0.9}


def test_relatorio_adulterado_reprova(tmp_path):
    base = {"modelos": {"m": {"relatorio": "r.json", "caminho": "teste", **REF}}}
    (tmp_path / "r.json").write_text(json.dumps({"teste": {"f1_macro": 0.5, "ece": 0.0, "troca": 0}}))
    falhas, _ = verificar(base, raiz=tmp_path)
    assert falhas and "f1_macro" in falhas[0]


def test_linha_base_versionada_passa_com_os_relatorios_do_repositorio():
    falhas, resumo = verificar(json.loads(LINHA_BASE.read_text(encoding="utf-8")))
    assert falhas == [], falhas
    assert len(resumo) >= 4
