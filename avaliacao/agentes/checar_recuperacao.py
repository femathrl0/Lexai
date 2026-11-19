"""Checa o Agente de Pesquisa sem LLM: a fonte esperada de cada pergunta entra entre as evidências?

    uv run --group worker python -m avaliacao.agentes.checar_recuperacao [--sem-vetor] [--sem-reranker] [--sem-expansao]

Usa a mesma Triagem e a mesma expansão de consulta do sistema multiagente, o `BuscadorLocal` e o recorte de
jurisprudência de corpus/jurisprudencia/. Roda em CPU em poucos minutos (embeddings ficam em cache).
Saída: avaliacao/agentes/resultados/<data>_recuperacao[...].{json,md}
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path

from worker.evidencia import guardas
from worker.evidencia.agentes.buscadores import BuscadorLocal
from worker.evidencia.agentes.expansao import expandir
from worker.evidencia.agentes.montagem import JURISPRUDENCIA_PADRAO

AQUI = Path(__file__).resolve().parent


def _alvos(caso: dict) -> list[str]:
    """Fontes aceitas: `fontes_esperadas` (lista) ou `fonte_esperada` (texto)."""
    return caso.get("fontes_esperadas") or ([caso["fonte_esperada"]] if caso.get("fonte_esperada") else [])


def _bate(alvo: str, fonte: str) -> bool:
    # "CLT, Art. 477" casa com "Art. 477"; "Súmula 244" casa com "Súmula 244 do TST"; "ADCT, Art. 10" exige ADCT.
    norma, _, art = alvo.rpartition(", ")
    if norma and norma not in fonte:
        return False
    return re.search(rf"{re.escape(art or alvo)}(?:º)?(?![\w-])", fonte) is not None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sem-vetor", action="store_true")
    ap.add_argument("--sem-reranker", action="store_true")
    ap.add_argument("--sem-expansao", action="store_true")
    ap.add_argument("--sem-jurisprudencia", action="store_true")
    ap.add_argument("--pouca-memoria", action="store_true",
                    help="nunca carrega BGE-M3 e reranker juntos: vetores das consultas primeiro, reranker depois")
    ap.add_argument("--por-fonte", type=int, default=3)
    a = ap.parse_args()

    juris = None if a.sem_jurisprudencia or not JURISPRUDENCIA_PADRAO.exists() else JURISPRUDENCIA_PADRAO
    casos = [json.loads(linha) for linha in (AQUI / "perguntas_demo.jsonl").read_text(encoding="utf-8").splitlines()
             if linha.strip()]
    consultas = {}
    for c in casos:
        r = guardas.verificar_entrada(c["pergunta"])
        if r.acao in ("responder", "orientar_sem_aconselhar"):
            consultas[c["id"]] = r.pergunta_sanitizada if a.sem_expansao else expandir(r.pergunta_sanitizada)[0]
    b = BuscadorLocal(jurisprudencia=juris, usar_vetor=not a.sem_vetor,
                      usar_reranker=not a.sem_reranker and not a.pouca_memoria)
    if a.pouca_memoria and b.encoder is not None:
        # Mesmo resultado do caminho normal, em duas fases: ranking vetorial de cada consulta, solta o BGE-M3,
        # carrega o reranker. Serve para máquinas de 8 GB.
        import gc

        from sentence_transformers import CrossEncoder
        rankings = {q: b._vetor(q, 30) for q in consultas.values()}
        b.encoder = None
        gc.collect()
        b._vetor = lambda consulta, k: rankings[consulta][:k]
        if not a.sem_reranker:
            b.reranker = CrossEncoder("BAAI/bge-reranker-v2-m3", max_length=256)
    res = []
    for c in casos:
        if c["id"] not in consultas:
            continue
        trechos = b.buscar(consultas[c["id"]], por_fonte=a.por_fonte)
        fontes = [t.fonte for t in trechos]
        alvos = _alvos(c)
        achados = {alvo: any(_bate(alvo, f) for f in fontes) for alvo in alvos}
        res.append(dict(id=c["id"], alvos=alvos, achados=achados, ok=all(achados.values()) if alvos else None,
                        fontes=fontes, notas=[t.nota_reranker for t in trechos]))
        print(f"{c['id']:>14} {'✅' if res[-1]['ok'] else ('—' if res[-1]['ok'] is None else '❌')} {fontes}", flush=True)

    config = "-".join(x for x, on in (("sem-vetor", a.sem_vetor), ("sem-reranker", a.sem_reranker),
                                     ("sem-expansao", a.sem_expansao), ("sem-juris", juris is None)) if on)
    nome = f"{date.today():%Y-%m-%d}_recuperacao" + (f"_{config}" if config else "")
    saida = AQUI / "resultados" / nome
    com_alvo = [x for x in res if x["ok"] is not None]
    linhas = [f"# Recuperação do Agente de Pesquisa — {date.today():%d/%m/%Y}\n",
              f"Buscador `{b.versao}` · vetor {'não' if a.sem_vetor else 'BGE-M3'} · reranker "
              f"{'não' if a.sem_reranker else 'bge-reranker-v2-m3'} · expansão {'não' if a.sem_expansao else 'sim'} · "
              f"jurisprudência {'não' if juris is None else juris.name} · {a.por_fonte} por tipo de fonte\n",
              f"**Perguntas com todas as fontes esperadas entre as evidências: "
              f"{sum(x['ok'] for x in com_alvo)}/{len(com_alvo)}**\n",
              "| id | fontes esperadas | evidências entregues |", "|---|---|---|"]
    for x in res:
        esperadas = ", ".join(f"{k} {'✅' if v else '❌'}" for k, v in x["achados"].items()) or "—"
        linhas.append(f"| {x['id']} | {esperadas} | {'; '.join(x['fontes'])} |")
    saida.with_suffix(".json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    saida.with_suffix(".md").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print("\n".join(linhas[:3]), f"\n→ {saida}.md")


if __name__ == "__main__":
    main()
