"""Benchmark dos rerankers candidatos (issue #10, RF06): nDCG, recall e MRR sobre pares (pergunta, trecho).

Fonte da relevância, nesta ordem:
  1. avaliacao/pares_ouro/reranker_legislacao.csv — pares-ouro da Cientista de dados + Curadoria (relevância 0–2);
  2. enquanto (1) não existe: perguntas aprovadas de legislação (avaliacao/dados/legislacao) com as referências
     aprovadas como relevância 2 e o resto do conjunto de candidatos como 0 (binário, provisório).

Todos os rerankers reordenam o MESMO conjunto de candidatos por pergunta: união do top-K denso (BGE-M3) e do
top-K por palavra-chave, fundidos por RRF — é o que o recuperador híbrido entrega ao reranker. Assim a comparação
mede só o reranker. A escolha é feita no dev; o teste congelado só é medido.

Também exporta o conjunto de candidatos para anotação graduada:
avaliacao/pares_ouro/reranker_legislacao_para_anotar.csv.

Uso:
    python -m treino.benchmark_rerankers
    python -m treino.benchmark_rerankers --rerankers BAAI/bge-reranker-v2-m3 --sem-mlflow
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import time
import unicodedata

from treino.comum import RAIZ, RELATORIOS, salvar_json, sha256_arquivo
from treino.metricas import ndcg_at_k, recall_at_k, reciprocal_rank

DIR_LEG = RAIZ / "avaliacao" / "dados" / "legislacao"
CHUNKS = RAIZ / "dados" / "chunks" / "legislacao" / "chunks_A_artigo.json"
PARES_OURO = RAIZ / "avaliacao" / "pares_ouro" / "reranker_legislacao.csv"
PARA_ANOTAR = RAIZ / "avaliacao" / "pares_ouro" / "reranker_legislacao_para_anotar.csv"
CACHE = RAIZ / "dados" / "output" / "benchmark_rerankers"

RERANKERS_PADRAO = [
    "BAAI/bge-reranker-v2-m3",
    "Alibaba-NLP/gte-multilingual-reranker-base",
    "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
    "unicamp-dl/mMiniLM-L6-v2-pt-v2",
]
PRECISA_REMOTE_CODE = {"Alibaba-NLP/gte-multilingual-reranker-base"}
KS = (1, 3, 5, 10)


# ---------------------------------------------------------------- funções puras
def chave_artigo(norma: str, dispositivo: str) -> str:
    d = unicodedata.normalize("NFKC", dispositivo).replace("°", "o").strip().lower()  # NFKC: º -> o
    d = re.sub(r"\s+", " ", d)
    return f"{norma.strip()}::{d}"


def rrf(rankings: list[list[str]], k: int = 60) -> list[str]:
    nota: dict[str, float] = {}
    for ranking in rankings:
        for pos, item in enumerate(ranking):
            nota[item] = nota.get(item, 0.0) + 1.0 / (k + pos + 1)
    return sorted(nota, key=lambda x: -nota[x])


def metricas_ranking(ordem: list[str], relevancia: dict[str, float]) -> dict[str, float]:
    rels = [relevancia.get(i, 0.0) for i in ordem]
    todas = [r for r in relevancia.values() if r > 0]
    n_rel = len(todas)
    out = {f"ndcg@{k}": ndcg_at_k(rels, todas, k) for k in KS}
    out.update({f"recall@{k}": recall_at_k(rels, n_rel, k) for k in KS})
    out["mrr@10"] = reciprocal_rank(rels, 10)
    return out


# ---------------------------------------------------------------- dados
def carregar_artigos() -> tuple[list[str], list[str], list[str]]:
    artigos = json.loads(CHUNKS.read_text(encoding="utf-8"))
    ids, textos_busca, textos_rerank = [], [], []
    vistos = set()
    for a in artigos:
        cid = chave_artigo(a["caminho_relativo"], a["artigo_ref"])
        if cid in vistos:
            continue
        vistos.add(cid)
        ids.append(cid)
        textos_busca.append(a["conteudo_chunk"])
        textos_rerank.append(a["corpo_chunk"])
    return ids, textos_busca, textos_rerank


def carregar_perguntas() -> list[dict]:
    """Perguntas aprovadas com relevância por artigo. Usa os pares-ouro graduados se existirem."""
    perguntas = []
    for split in ("dev", "test"):
        for q in json.loads((DIR_LEG / f"eval_dataset_{split}_aprovado.json").read_text(encoding="utf-8")):
            if q.get("elegivel_metricas") in (True, "True", "true"):
                perguntas.append(
                    {"query_id": q["query_id"], "pergunta": q["pergunta"], "split": split, "relevancia": {}}
                )
    por_id = {q["query_id"]: q for q in perguntas}
    if PARES_OURO.exists():
        fonte = f"pares-ouro graduados ({PARES_OURO.relative_to(RAIZ)})"
        with PARES_OURO.open(encoding="utf-8") as f:
            for linha in csv.DictReader(f):
                if linha["query_id"] in por_id and linha.get("relevancia", "").strip() != "":
                    por_id[linha["query_id"]]["relevancia"][linha["artigo_id"]] = float(linha["relevancia"])
    else:
        fonte = "provisória: referências aprovadas de legislação = 2, demais candidatos = 0"
        for r in json.loads((DIR_LEG / "referencias_aprovadas.json").read_text(encoding="utf-8")):
            if r["query_id"] in por_id and str(r.get("status_revisao", "")).lower() == "aprovado":
                por_id[r["query_id"]]["relevancia"][chave_artigo(r["norma"], r["dispositivo"])] = 2.0
    return perguntas, fonte


# ---------------------------------------------------------------- recuperação (gera o conjunto de candidatos)
def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower()


def candidatos(perguntas, ids, textos_busca, k_cada: int, k_pool: int, device: str) -> dict[str, dict[str, list[str]]]:
    import numpy as np
    from sentence_transformers import SentenceTransformer
    from sklearn.feature_extraction.text import TfidfVectorizer

    CACHE.mkdir(parents=True, exist_ok=True)
    cache = CACHE / f"bge_m3_{sha256_arquivo(CHUNKS)[:12]}.npy"
    enc = SentenceTransformer("BAAI/bge-m3", device=device)
    enc.max_seq_length = 1024
    if cache.exists():
        emb = np.load(cache)
    else:
        print(f"gerando embeddings de {len(ids)} artigos (cache em {cache.name})…", flush=True)
        emb = enc.encode(textos_busca, batch_size=16, normalize_embeddings=True, show_progress_bar=True)
        np.save(cache, emb)
    qemb = enc.encode([q["pergunta"] for q in perguntas], normalize_embeddings=True)
    denso = np.argsort(-(qemb @ emb.T), axis=1)[:, :k_cada]

    # palavra-chave: TF-IDF sem acento com bigramas — proxy local do full-text do Postgres (Eng. de IA)
    tfidf = TfidfVectorizer(preprocessor=_sem_acento, ngram_range=(1, 2), sublinear_tf=True, min_df=1)
    X = tfidf.fit_transform(textos_busca)
    lex = np.argsort(-(tfidf.transform([q["pergunta"] for q in perguntas]) @ X.T).toarray(), axis=1)[:, :k_cada]

    out = {}
    for i, q in enumerate(perguntas):
        d = [ids[j] for j in denso[i]]
        lx = [ids[j] for j in lex[i]]
        out[q["query_id"]] = {"denso": d, "palavra_chave": lx, "hibrido_rrf": rrf([d, lx])[:k_pool]}
    del enc
    return out


# ---------------------------------------------------------------- rerankers
class _Reranker:
    def __init__(self, repo: str, device: str):
        from sentence_transformers import CrossEncoder

        kw = {"trust_remote_code": True} if repo in PRECISA_REMOTE_CODE else {}
        self.repo = repo
        self.ce = CrossEncoder(repo, device=device, max_length=512, **kw)

    def notas(self, pergunta: str, textos: list[str]) -> list[float]:
        import numpy as np

        s = np.asarray(self.ce.predict([(pergunta, t) for t in textos], batch_size=16))
        if s.ndim == 2:  # modelos com 2 rótulos (não relevante, relevante): usa o logit da classe relevante
            s = s[:, -1]
        return s.tolist()


def avaliar_ordens(perguntas, ordens: dict[str, list[str]]) -> dict[str, dict[str, float]]:
    por_split: dict[str, dict[str, float]] = {}
    for split in ("dev", "test"):
        qs = [q for q in perguntas if q["split"] == split and any(v > 0 for v in q["relevancia"].values())]
        ms = [metricas_ranking(ordens[q["query_id"]], q["relevancia"]) for q in qs]
        por_split[split] = {k: statistics.fmean(m[k] for m in ms) for k in ms[0]} | {"perguntas": len(qs)}
    return por_split


def separacao_negativas(perguntas, notas_top1: dict[str, float]) -> dict[str, float] | None:
    """Quão bem a nota do 1º colocado separa pergunta com resposta de pergunta sem resposta no corpus (AUC)."""
    pos = [notas_top1[q["query_id"]] for q in perguntas if any(v > 0 for v in q["relevancia"].values())]
    neg = [notas_top1[q["query_id"]] for q in perguntas if not any(v > 0 for v in q["relevancia"].values())]
    if not pos or not neg:
        return None
    auc = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg))
    return {
        "auc_top1": auc,
        "nota_top1_media_com_resposta": statistics.fmean(pos),
        "nota_top1_media_sem_resposta": statistics.fmean(neg),
        "sem_resposta": len(neg),
    }


# ---------------------------------------------------------------- principal
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rerankers", nargs="+", default=RERANKERS_PADRAO)
    ap.add_argument("--k-cada", type=int, default=20, help="candidatos de cada busca antes do RRF")
    ap.add_argument("--k-pool", type=int, default=30, help="candidatos entregues ao reranker")
    ap.add_argument("--device", default="mps")
    ap.add_argument("--sem-mlflow", action="store_true")
    a = ap.parse_args()

    import datetime as dt

    from treino.comum import commit_atual, iniciar_mlflow, tags_padrao

    ids, textos_busca, textos_rerank = carregar_artigos()
    texto_de = dict(zip(ids, textos_rerank, strict=True))
    perguntas, fonte = carregar_perguntas()
    print(f"{len(ids)} artigos · {len(perguntas)} perguntas · relevância: {fonte}", flush=True)
    cand = candidatos(perguntas, ids, textos_busca, a.k_cada, a.k_pool, a.device)

    # candidatos para a Cientista de dados anotar 0–2 (vira avaliacao/pares_ouro/reranker_legislacao.csv)
    PARA_ANOTAR.parent.mkdir(parents=True, exist_ok=True)
    with PARA_ANOTAR.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["query_id", "split", "pergunta", "artigo_id", "texto", "relevancia_provisoria", "relevancia"])
        for q in perguntas:
            for aid in cand[q["query_id"]]["hibrido_rrf"]:
                w.writerow(
                    [
                        q["query_id"],
                        q["split"],
                        q["pergunta"],
                        aid,
                        texto_de[aid][:1500],
                        int(q["relevancia"].get(aid, 0)),
                        "",
                    ]
                )

    resultados: dict[str, dict] = {}
    # recall do conjunto de candidatos (teto de qualquer reranker) e ordens sem reranker
    resultados["teto_conjunto_candidatos"] = {
        s: {
            "recall@pool": statistics.fmean(
                recall_at_k(
                    [q["relevancia"].get(i, 0) for i in cand[q["query_id"]]["hibrido_rrf"]],
                    sum(1 for v in q["relevancia"].values() if v > 0),
                    a.k_pool,
                )
                for q in perguntas
                if q["split"] == s and any(v > 0 for v in q["relevancia"].values())
            )
        }
        for s in ("dev", "test")
    }
    for nome in ("palavra_chave", "denso", "hibrido_rrf"):
        resultados[f"sem_reranker:{nome}"] = {
            "metricas": avaliar_ordens(perguntas, {k: v[nome] for k, v in cand.items()})
        }

    for repo in a.rerankers:
        print(f"reranker {repo}…", flush=True)
        try:
            t0 = time.perf_counter()
            rr = _Reranker(repo, a.device)
            carga = time.perf_counter() - t0
        except Exception as e:  # noqa: BLE001 — candidato que não carrega fica registrado como falha
            print(f"  falhou ao carregar: {e}")
            resultados[f"reranker:{repo}"] = {"erro": f"{type(e).__name__}: {e}"}
            continue
        ordens, top1, tempos = {}, {}, []
        for q in perguntas:
            pool = cand[q["query_id"]]["hibrido_rrf"]
            t0 = time.perf_counter()
            notas = rr.notas(q["pergunta"], [texto_de[i] for i in pool])
            tempos.append(time.perf_counter() - t0)
            ordem = [i for _, i in sorted(zip(notas, pool, strict=True), key=lambda x: -x[0])]
            ordens[q["query_id"]] = ordem
            top1[q["query_id"]] = max(notas)
        resultados[f"reranker:{repo}"] = {
            "metricas": avaliar_ordens(perguntas, ordens),
            "separacao_sem_resposta": separacao_negativas(perguntas, top1),
            "carga_s": carga,
            "latencia_por_pergunta_s": {"p50": statistics.median(tempos), "max": max(tempos)},
            "pares_por_pergunta": a.k_pool,
        }
        m = resultados[f"reranker:{repo}"]["metricas"]
        print(
            f"  dev nDCG@5 {m['dev']['ndcg@5']:.3f} · teste nDCG@5 {m['test']['ndcg@5']:.3f} · "
            f"{statistics.median(tempos):.2f}s/pergunta",
            flush=True,
        )
        del rr

    validos = {k: v for k, v in resultados.items() if k.startswith("reranker:") and "metricas" in v}
    escolhido = max(
        validos,
        key=lambda k: (validos[k]["metricas"]["dev"]["ndcg@5"], validos[k]["metricas"]["dev"]["mrr@10"]),
        default=None,
    )
    resumo = {
        "quando": dt.datetime.now().isoformat(timespec="seconds"),
        "commit": commit_atual(),
        "relevancia": fonte,
        "artigos": len(ids),
        "perguntas": {s: sum(q["split"] == s for q in perguntas) for s in ("dev", "test")},
        "k_cada": a.k_cada,
        "k_pool": a.k_pool,
        "escolhido_no_dev": escolhido,
        "resultados": resultados,
    }
    js = salvar_json(resumo, RELATORIOS / "benchmark_rerankers.json")
    md = RELATORIOS / "benchmark_rerankers.md"
    md.write_text(_md(resumo), encoding="utf-8")
    print(f"relatório: {md}")

    if not a.sem_mlflow:
        mlflow = iniciar_mlflow("benchmark_rerankers")
        for nome, r in resultados.items():
            if "metricas" not in r:
                continue
            with mlflow.start_run(run_name=nome):
                mlflow.set_tags(
                    tags_padrao(tarefa="reranker", relevancia=fonte, chunks_sha256=sha256_arquivo(CHUNKS)[:16])
                )
                mlflow.log_params({"k_cada": a.k_cada, "k_pool": a.k_pool, "modelo": nome})
                for split, ms in r["metricas"].items():
                    mlflow.log_metrics({f"{split}.{k.replace('@', '_at_')}": float(v) for k, v in ms.items()})
                if r.get("latencia_por_pergunta_s"):
                    mlflow.log_metric("latencia_p50_s", r["latencia_por_pergunta_s"]["p50"])
                if r.get("separacao_sem_resposta"):
                    mlflow.log_metric("auc_top1_sem_resposta", r["separacao_sem_resposta"]["auc_top1"])
                mlflow.log_artifact(str(js))
        print("registrado no MLflow (experimento benchmark_rerankers)")


def _md(r: dict) -> str:
    res = r["resultados"]
    teto = res["teto_conjunto_candidatos"]
    cab = "| Configuração | nDCG@3 | nDCG@5 | nDCG@10 | Recall@1 | Recall@3 | Recall@5 | MRR@10 |"
    lin = [
        "# Benchmark dos rerankers — legislação",
        "",
        f"Gerado por `python -m treino.benchmark_rerankers` em {r['quando']} · commit `{r['commit'][:12]}`.",
        "",
        f"- **Relevância:** {r['relevancia']}.",
        f"- **Corpus:** {r['artigos']} artigos (estratégia A) · perguntas (com e sem resposta): "
        f"dev {r['perguntas']['dev']}, teste {r['perguntas']['test']}.",
        f"- **Candidatos por pergunta:** top-{r['k_cada']} denso (BGE-M3) ∪ top-{r['k_cada']} palavra-chave, "
        f"RRF, primeiros {r['k_pool']}. Teto (recall do conjunto): "
        f"dev {teto['dev']['recall@pool']:.2f}, teste {teto['test']['recall@pool']:.2f}.",
        f"- **Escolha no dev (nDCG@5, desempate MRR):** `{r['escolhido_no_dev']}`.",
        "",
    ]
    for split, titulo in (("dev", "Desenvolvimento (escolha)"), ("test", "Teste congelado (só medida)")):
        lin += [f"## {titulo}", "", cab, "|---|" + "---:|" * 7]
        for nome, x in res.items():
            if "metricas" not in x:
                continue
            m = x["metricas"][split]
            lin.append(
                f"| {nome} | {m['ndcg@3']:.3f} | {m['ndcg@5']:.3f} | {m['ndcg@10']:.3f} | {m['recall@1']:.3f} | "
                f"{m['recall@3']:.3f} | {m['recall@5']:.3f} | {m['mrr@10']:.3f} |"
            )
        lin.append("")
    lin += [
        "## Custo e separação de perguntas sem resposta",
        "",
        "| Reranker | Carga (s) | Latência p50 por pergunta (s) | AUC nota top-1 (com × sem resposta) |",
        "|---|---:|---:|---:|",
    ]
    for nome, x in res.items():
        if not nome.startswith("reranker:"):
            continue
        if "erro" in x:
            lin.append(f"| {nome} | falhou: {x['erro'][:80]} | | |")
            continue
        sep = x.get("separacao_sem_resposta")
        lin.append(
            f"| {nome} | {x['carga_s']:.1f} | {x['latencia_por_pergunta_s']['p50']:.2f} | {sep['auc_top1']:.2f} |"
            if sep
            else f"| {nome} | {x['carga_s']:.1f} | {x['latencia_por_pergunta_s']['p50']:.2f} | — |"
        )
    return "\n".join(lin) + "\n"


if __name__ == "__main__":
    main()
