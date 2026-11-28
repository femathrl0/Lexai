"""Classificador de intenção da guarda de entrada (issue #24, RF07/RNF06): regras × TF-IDF de caracteres + LR.

    uv run --group treino python -m treino.intencao gerar     # (re)gera o rascunho avaliacao/dados/intencao/casos_v1.jsonl
    uv run --group treino python -m treino.intencao avaliar   # compara e grava treino/relatorios/intencao.{json,md}

**Dados.** As regras de `worker/evidencia/guardas.verificar_entrada` acertam os 35 casos reais do repositório (20 de
guardas + 15 da demo), poucos demais para treinar ou para mostrar diferença. `gerar` monta um rascunho maior e
determinístico por moldes (pergunta informativa, caso concreto, consulta individual, fora do escopo, outra jurisdição,
institucional), com paráfrases e erros de digitação. **Os rótulos são do molde, não de uma pessoa**: o arquivo fica
marcado "aguarda aceite" da Cientista de dados (casos armadilha) e não substitui os casos reais.

**Avaliação.** O modelo treina só no rascunho (divisão por molde, para não decorar frase) e é testado (1) na parte de
teste do rascunho e (2) nos 35 casos reais. Erro grave: pergunta de caso concreto ou consulta individual tratada como
informativa (o sistema responderia como se fosse orientação). Regra 0004: as regras ficam em uso se o modelo não
vencer nos casos reais.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter

from treino.comum import RAIZ, RELATORIOS, salvar_json

ARQUIVO = RAIZ / "avaliacao" / "dados" / "intencao" / "casos_v1.jsonl"
REAIS = (RAIZ / "avaliacao" / "dados" / "integracao" / "casos_guardrails_entrada.jsonl",
         RAIZ / "avaliacao" / "agentes" / "perguntas_demo.jsonl")
ACOES = ("responder", "orientar_sem_aconselhar", "consulta_individual", "fora_escopo", "outra_jurisdicao", "institucional")
GRAVES = {("orientar_sem_aconselhar", "responder"), ("consulta_individual", "responder")}

TEMAS = ["horas extras", "aviso prévio", "férias", "FGTS", "décimo terceiro", "adicional noturno", "justa causa",
         "intervalo para almoço", "licença-maternidade", "estabilidade da gestante", "verbas rescisórias", "banco de horas",
         "insalubridade", "periculosidade", "seguro-desemprego", "trabalho intermitente", "home office", "vale-transporte"]
MOLDES = {
    "responder": ["O que a CLT diz sobre {t}?", "Como funciona {t} segundo a lei?", "Quais são as regras de {t}?",
                  "Explique {t} na legislação trabalhista.", "qual o prazo legal para {t}", "o que e {t} na clt",
                  "Existe limite legal para {t}?", "Quem tem direito a {t} pela lei?"],
    "orientar_sem_aconselhar": ["Fui demitido e não recebi {t}, devo processar a empresa?",
                                "Meu chefe não paga {t}, o que eu faço?", "Trabalho sem receber {t}, posso pedir demissão?",
                                "minha empresa cortou {t}, vale a pena entrar na justiça?",
                                "Estou grávida e me negaram {t}, devo recorrer?",
                                "Eu tenho direito a {t} no meu caso? fui mandado embora ontem"],
    "consulta_individual": ["Como está o andamento do meu processo de {t}?", "Qual a situação da minha reclamação sobre {t}?",
                            "Meu processo 0001234-56.2024.5.10.0001 sobre {t} já tem sentença?",
                            "quando sai o alvará do meu processo de {t}", "Consulte o meu recurso sobre {t} no tribunal"],
    "fora_escopo": ["Como declarar imposto de renda sobre {x}?", "Como faço divórcio consensual com {x}?",
                    "Qual a pena por {x} no código penal?", "Como recorrer de multa de trânsito por {x}?",
                    "Quanto custa abrir uma empresa de {x}?", "Me ajude a investir em {x}"],
    "outra_jurisdicao": ["Como funciona {t} em Portugal?", "Quais as regras de {t} nos Estados Unidos?",
                         "Na Argentina existe {t}?", "Como é {t} na lei da Espanha?", "{t} no Canadá é igual ao Brasil?"],
    "institucional": ["Quem criou esta plataforma?", "Você é um chatbot de qual empresa?", "Como funciona este aplicativo?",
                      "Seus dados ficam guardados no site?", "Quem é o responsável por este app?",
                      "A plataforma cobra para usar?"],
}
OUTROS = ["ações", "criptomoedas", "minha casa", "furto", "excesso de velocidade", "padaria", "herança", "pensão alimentícia"]


# ---------------------------------------------------------------- funções puras (testadas no CI)
def _ruido(frase: str, rng: random.Random) -> str:
    """Paráfrase leve: minúsculas, sem acento ou uma letra trocada — como a pessoa digita no celular."""
    import unicodedata

    r = rng.random()
    if r < 0.25:
        return frase.lower()
    if r < 0.45:
        return "".join(c for c in unicodedata.normalize("NFKD", frase) if not unicodedata.combining(c))
    if r < 0.6 and len(frase) > 10:
        i = rng.randrange(1, len(frase) - 1)
        return frase[:i] + frase[i + 1] + frase[i] + frase[i + 2:]
    return frase


def gerar_casos(semente: int = 2026) -> list[dict]:
    rng = random.Random(semente)
    casos = []
    for acao, moldes in MOLDES.items():
        for m_id, molde in enumerate(moldes):
            preenchimentos = OUTROS if "{x}" in molde else TEMAS if "{t}" in molde else [""]
            for p in preenchimentos:
                frase = _ruido(molde.format(t=p, x=p), rng)
                cid = hashlib.sha256(f"{acao}:{frase}".encode()).hexdigest()[:10]
                casos.append({"id": f"int-{cid}", "pergunta": frase, "acao_esperada": acao, "molde": f"{acao}:{m_id}",
                              "status": "rascunho por molde — aguarda aceite da Cientista de dados"})
    vistos, unicos = set(), []
    for c in casos:
        if c["pergunta"] not in vistos:
            vistos.add(c["pergunta"])
            unicos.append(c)
    return unicos


def divisao_por_molde(molde: str) -> str:
    """O mesmo molde nunca aparece no treino e no teste (senão o modelo decora a frase)."""
    b = int(hashlib.sha256(f"lexai-intencao-v1:{molde}".encode()).hexdigest(), 16) % 100
    return "teste" if b < 30 else "treino"


def avaliar(y_true: list[str], y_pred: list[str]) -> dict:
    from treino.metricas import f1_por_classe

    por = f1_por_classe(y_true, y_pred, ACOES)
    presentes = [a for a in ACOES if por[a]["suporte"]]
    return {"acuracia": sum(a == b for a, b in zip(y_true, y_pred, strict=True)) / len(y_true),
            "f1_macro": sum(por[a]["f1"] for a in presentes) / len(presentes), "por_classe": por,
            "erros_graves": sum((a, b) in GRAVES for a, b in zip(y_true, y_pred, strict=True)), "n": len(y_true)}


# ---------------------------------------------------------------- execução
def _reais() -> list[dict]:
    out = []
    for arq in REAIS:
        for linha in arq.read_text(encoding="utf-8").splitlines():
            if linha.strip():
                c = json.loads(linha)
                out.append({"pergunta": c["pergunta"], "acao_esperada": c["acao_esperada"]})
    return out


def regras(pergunta: str) -> str:
    from worker.evidencia.guardas import verificar_entrada

    return verificar_entrada(pergunta).acao


def rodar(sem_mlflow: bool) -> dict:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline

    casos = [json.loads(x) for x in ARQUIVO.read_text(encoding="utf-8").splitlines() if x.strip()]
    treino = [c for c in casos if divisao_por_molde(c["molde"]) == "treino"]
    teste = [c for c in casos if divisao_por_molde(c["molde"]) == "teste"]
    reais = _reais()
    modelo = make_pipeline(TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True, strip_accents="unicode",
                                           lowercase=True),
                           LogisticRegression(C=10, class_weight="balanced", max_iter=3000))
    modelo.fit([c["pergunta"] for c in treino], [c["acao_esperada"] for c in treino])
    res = {}
    for nome, conj in (("rascunho_teste", teste), ("casos_reais", reais)):
        y = [c["acao_esperada"] for c in conj]
        res[nome] = {"regras": avaliar(y, [regras(c["pergunta"]) for c in conj]),
                     "tfidf_char_lr": avaliar(y, list(modelo.predict([c["pergunta"] for c in conj])))}
    r, m = res["casos_reais"]["regras"], res["casos_reais"]["tfidf_char_lr"]
    vence = m["f1_macro"] >= r["f1_macro"] + 0.02 and m["erros_graves"] <= r["erros_graves"]
    rel = {"casos_rascunho": len(casos), "treino": len(treino), "teste": len(teste), "reais": len(reais),
           "distribuicao": dict(Counter(c["acao_esperada"] for c in casos)), "resultados": res,
           "decisao": "modelo vira candidato" if vence else "regras continuam em uso (o modelo não vence nos casos reais)"}
    if not sem_mlflow:
        from treino.comum import iniciar_mlflow, sha256_arquivo, tags_padrao

        mlflow = iniciar_mlflow("intencao_guarda")
        for variante in ("regras", "tfidf_char_lr"):
            with mlflow.start_run(run_name=variante):
                mlflow.set_tags(tags_padrao(tarefa="intencao_guarda", variante=variante,
                                            **{"dados.sha256": sha256_arquivo(ARQUIVO)}))
                for conj in res:
                    x = res[conj][variante]
                    mlflow.log_metrics({f"{conj}.f1_macro": x["f1_macro"], f"{conj}.erros_graves": x["erros_graves"]})
    return rel


def markdown(rel: dict) -> str:
    lin = ["# Intenção da guarda de entrada: regras × TF-IDF de caracteres + LR", "",
           f"Rascunho por molde: {rel['casos_rascunho']} casos ({rel['treino']} treino / {rel['teste']} teste, divisão por "
           f"molde) · {rel['reais']} casos reais do repositório. **Rótulos do rascunho aguardam aceite.**", "",
           "| Conjunto | Variante | F1 macro | Acurácia | Erros graves |", "|---|---|---:|---:|---:|"]
    for conj, vs in rel["resultados"].items():
        for v, x in vs.items():
            lin.append(f"| {conj} | {v} | {x['f1_macro']:.3f} | {x['acuracia']:.3f} | {x['erros_graves']} |")
    lin += ["", f"**Decisão (0004):** {rel['decisao']}.", "",
            "Erro grave: caso concreto ou consulta individual tratado como pergunta informativa."]
    return "\n".join(lin) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("gerar")
    av = sub.add_parser("avaliar")
    av.add_argument("--sem-mlflow", action="store_true")
    a = ap.parse_args()
    if a.cmd == "gerar":
        ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
        casos = gerar_casos()
        ARQUIVO.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in casos), encoding="utf-8")
        print(f"{len(casos)} casos → {ARQUIVO}", dict(Counter(c["acao_esperada"] for c in casos)))
    else:
        rel = rodar(a.sem_mlflow)
        salvar_json(rel, RELATORIOS / "intencao.json")
        (RELATORIOS / "intencao.md").write_text(markdown(rel), encoding="utf-8")
        print(markdown(rel))


if __name__ == "__main__":
    main()

