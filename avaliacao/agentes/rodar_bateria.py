"""Roda o sistema multiagente sobre avaliacao/agentes/perguntas_demo.jsonl e mede a colaboração.

    uv run --group worker python -m avaliacao.agentes.rodar_bateria --modelo qwen3:8b
Saídas: avaliacao/agentes/resultados/<data>_<modelo>.{json,md} (rastros completos no JSON).
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
from datetime import date
from pathlib import Path

from avaliacao.agentes.checar_recuperacao import _alvos, _bate
from worker.evidencia.agentes import analise, comunicacao
from worker.evidencia.agentes.comunicacao import flesch_pt
from worker.evidencia.agentes.montagem import montar

AQUI = Path(__file__).resolve().parent


def _art(texto: str | None) -> str | None:
    m = re.search(r"Art\.\s*(\d+(?:-[A-Z])?)", texto or "")
    return m.group(1) if m else None


def avaliar(caso: dict, estado) -> dict:
    msgs = estado.rastro.mensagens
    tempos = {}
    for m in msgs:
        if m.ms is not None:
            tempos[m.de] = round(tempos.get(m.de, 0) + m.ms / 1000, 1)
    julg = [j for m in msgs if m.de == "validacao" for j in m.dados.get("julgamento", [])]
    esperado = _art(caso.get("fonte_esperada"))
    fontes = [t.fonte for t in (estado.evidencias.trechos if estado.evidencias else [])]
    texto = " ".join(f.texto for f in estado.resposta.frases)
    return dict(
        id=caso["id"], tipo=caso["tipo"], acao=estado.triagem.acao, acao_ok=estado.triagem.acao == caso["acao_esperada"],
        fonte_esperada=caso.get("fonte_esperada"), fontes=fontes,
        fonte_ok=None if not esperado else any(_art(f) == esperado for f in fontes),
        # Critério revisado em 19/11: todas as fontes de `fontes_esperadas` (norma + artigo/súmula) entre as evidências.
        todas_fontes_ok=None if not _alvos(caso) else all(any(_bate(a, f) for f in fontes) for a in _alvos(caso)),
        frases_geradas=len(estado.explicacao.frases) if estado.explicacao else 0,
        frases_liberadas=len(estado.resposta.frases),
        aprovacao_1a_validacao=(sum(j["aprovada"] for j in julg[:len(estado.explicacao.frases)]) /
                                max(1, len(estado.explicacao.frases))) if estado.explicacao else None,
        devolucoes=[m.para for m in msgs if m.tipo == "devolucao"],
        legibilidade=flesch_pt(texto) if texto else None, tempos=tempos,
        dado_pessoal_vazou=bool(re.search(r"\d{3}\.\d{3}\.\d{3}-\d{2}", texto)),
        resposta=[dict(texto=f.texto, fonte=f.fonte) for f in estado.resposta.frases], avisos=estado.resposta.avisos,
        rastro=[m.model_dump(mode="json") for m in msgs])


def tabela(res: list[dict], modelo: str) -> str:
    def media(xs):
        xs = [x for x in xs if x is not None]
        return f"{statistics.mean(xs):.2f}" if xs else "—"
    com_llm = [r for r in res if r["frases_geradas"]]
    linhas = [
        f"# Bateria do sistema multiagente — {date.today():%d/%m/%Y} — LLM `{modelo}`\n",
        f"Prompts `{analise.PROMPT_ID}` e `{comunicacao.PROMPT_ID}` · perguntas `avaliacao/agentes/perguntas_demo.jsonl`\n",
        "| Métrica | Valor |", "|---|---|",
        f"| Perguntas | {len(res)} |",
        f"| Ação correta da Triagem | {sum(r['acao_ok'] for r in res)}/{len(res)} |",
        f"| Fonte esperada entre as evidências | {sum(bool(r['fonte_ok']) for r in res if r['fonte_ok'] is not None)}/"
        f"{sum(r['fonte_ok'] is not None for r in res)} |",
        f"| Todas as fontes esperadas (norma + artigo/súmula) | "
        f"{sum(bool(r['todas_fontes_ok']) for r in res if r['todas_fontes_ok'] is not None)}/"
        f"{sum(r['todas_fontes_ok'] is not None for r in res)} |",
        f"| Aprovação na 1ª validação (média) | {media(r['aprovacao_1a_validacao'] for r in com_llm)} |",
        f"| Frases liberadas / geradas | {sum(r['frases_liberadas'] for r in com_llm)}/"
        f"{sum(r['frases_geradas'] for r in com_llm)} |",
        f"| Perguntas com devolução | {sum(bool(r['devolucoes']) for r in res)} |",
        f"| Legibilidade (Flesch PT, média) | {media(r['legibilidade'] for r in com_llm)} |",
        f"| Dado pessoal na resposta | {sum(r['dado_pessoal_vazou'] for r in res)} |",
        "| Tempo médio por agente (s) | " + ", ".join(
            f"{a} {media(r['tempos'].get(a) for r in com_llm)}" for a in ("pesquisa", "analise", "comunicacao", "validacao"))
        + " |",
        "\n| id | tipo | ação | fonte esperada | encontrada | liberadas/geradas | devoluções |", "|---|---|---|---|---|---|---|"]
    for r in res:
        linhas.append(f"| {r['id']} | {r['tipo']} | {r['acao']} {'✅' if r['acao_ok'] else '❌'} | "
                      f"{r['fonte_esperada'] or '—'} | "
                      f"{'—' if r['fonte_ok'] is None else ('✅' if r['fonte_ok'] else '❌')} | "
                      f"{r['frases_liberadas']}/{r['frases_geradas']} | {', '.join(r['devolucoes']) or '—'} |")
    return "\n".join(linhas) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--modelo")
    ap.add_argument("--buscador", default="local")
    ap.add_argument("--sem-nli", action="store_true")
    ap.add_argument("--limite", type=int)
    a = ap.parse_args()
    casos = [json.loads(linha) for linha in (AQUI / "perguntas_demo.jsonl").read_text(encoding="utf-8").splitlines() if linha]
    orq = montar(a.buscador, a.modelo, nli=not a.sem_nli)
    res = []
    for caso in casos[: a.limite]:
        print(f"→ {caso['id']}: {caso['pergunta'][:80]}", flush=True)
        res.append(avaliar(caso, orq.responder(caso["pergunta"])))
    modelo = orq.agentes["analise"].llm.modelo
    saida = AQUI / "resultados" / (f"{date.today():%Y-%m-%d}_{modelo.replace(':', '-')}_"
                                   f"{analise.PROMPT_ID.replace('/', '-')}")
    saida.parent.mkdir(exist_ok=True)
    saida.with_suffix(".json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    saida.with_suffix(".md").write_text(tabela(res, modelo), encoding="utf-8")
    print(tabela(res, modelo))


if __name__ == "__main__":
    main()
