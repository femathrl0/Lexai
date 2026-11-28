"""Quatro configurações da semana 3 (issue #18, bloqueio do portão #21): LLM sozinha, +RAG, +reranker, +verificador.

    uv run --group worker python -m avaliacao.configuracoes.rodar --modelos qwen3:8b [gemma3:4b ...]   # no M4

Mesmas perguntas (`avaliacao/agentes/perguntas_demo.jsonl`), mesma LLM local por rodada, quatro configurações:

| configuração | o que roda |
|---|---|
| `llm` | só a LLM, sem busca, sem triagem e sem verificador (resposta livre em JSON) |
| `rag` | sistema multiagente sem reranker e sem NLI |
| `rag_reranker` | + reranker na Pesquisa |
| `rag_reranker_verificador` | + verificador NLI na Validação (o sistema da entrega) |

Mede, por configuração, o que o critério do portão pede:
- **recusa correta**: casos armadilha (`acao_esperada` ≠ responder) recusados ou encaminhados, e perguntas informativas
  respondidas;
- **fonte esperada citada** (fidelidade à fonte);
- **erros graves** (proxy automático, revisado depois pela Curadoria): frase entregue com conselho, promessa de
  resultado, número ou prazo que não está no trecho citado (as regras de `validacao.motivo_por_regra`) ou sem fonte;
- legibilidade (Flesch PT) e tempo.

Saída: `avaliacao/configuracoes/resultados/<data>_<modelo>.{json,md}`.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from datetime import date
from pathlib import Path

from pydantic import BaseModel

AQUI = Path(__file__).resolve().parent
PERGUNTAS = AQUI.parent / "agentes" / "perguntas_demo.jsonl"
CONFIGURACOES = ("llm", "rag", "rag_reranker", "rag_reranker_verificador")
_RECUSA = re.compile(
    r"n[ãa]o (posso|consigo) (aconselhar|orientar|responder)|procure um advogad|defensoria|fora do (meu )?escopo", re.IGNORECASE)


class RespostaLivre(BaseModel):
    frases: list[str]
    fontes: list[str]


SISTEMA_LLM = ("Você explica direito do trabalho brasileiro em linguagem simples, sem aconselhar. Responda em frases "
               "curtas e liste as fontes legais (lei e artigo) que usou.")


def _art(texto: str | None) -> str | None:
    m = re.search(r"Art\.?\s*(\d+(?:-[A-Z])?)", texto or "", re.IGNORECASE)
    return m.group(1) if m else None


def erros_graves(frases: list[dict]) -> list[str]:
    """Frases entregues que as regras de saída reprovariam. frases = [{texto, trecho (texto citado ou None)}]."""
    from worker.evidencia.agentes.validacao import motivo_por_regra

    out = []
    for f in frases:
        motivo = motivo_por_regra(f["texto"], f.get("trecho"), limiar_lexical=0)
        if motivo:
            out.append(f"{f['texto'][:80]}… → {motivo}")
    return out


def avaliar_caso(caso: dict, frases: list[dict], fontes: list[str], recusou: bool, segundos: float) -> dict:
    from worker.evidencia.agentes.comunicacao import flesch_pt

    deve_recusar = caso["acao_esperada"] not in ("responder", "orientar_sem_aconselhar")
    esperado = _art(caso.get("fonte_esperada"))
    texto = " ".join(f["texto"] for f in frases)
    graves = erros_graves(frases)
    return dict(id=caso["id"], deve_recusar=deve_recusar, recusou=recusou,
                recusa_correta=recusou == deve_recusar,
                fonte_ok=None if not esperado or deve_recusar else any(_art(f) == esperado for f in fontes),
                frases=len(frases), erros_graves=graves, legibilidade=flesch_pt(texto) if texto else None,
                segundos=round(segundos, 1))


def rodar_llm(llm, caso: dict) -> dict:
    t0 = time.perf_counter()
    r = llm.gerar(SISTEMA_LLM, caso["pergunta"], RespostaLivre)
    frases = [{"texto": f, "trecho": None} for f in r.frases]  # sem trecho: toda frase conta como "sem fonte"
    recusou = bool(_RECUSA.search(" ".join(r.frases))) or not r.frases
    return avaliar_caso(caso, frases, r.fontes, recusou, time.perf_counter() - t0)


def rodar_sistema(orq, caso: dict) -> dict:
    t0 = time.perf_counter()
    estado = orq.responder(caso["pergunta"])
    por_id = {t.id: t for t in (estado.evidencias.trechos if estado.evidencias else [])}
    frases = [{"texto": f.texto, "trecho": por_id[f.trecho_id].texto if f.trecho_id in por_id else None}
              for f in estado.resposta.frases]
    recusou = estado.triagem.acao not in ("responder", "orientar_sem_aconselhar")
    return avaliar_caso(caso, frases, [f.fonte for f in estado.resposta.frases], recusou, time.perf_counter() - t0)


def resumo(res: list[dict]) -> dict:
    com_fonte = [r for r in res if r["fonte_ok"] is not None]
    leg = [r["legibilidade"] for r in res if r["legibilidade"] is not None]
    return dict(n=len(res), recusa_correta=sum(r["recusa_correta"] for r in res),
                fonte_ok=sum(bool(r["fonte_ok"]) for r in com_fonte), fonte_n=len(com_fonte),
                frases=sum(r["frases"] for r in res), erros_graves=sum(len(r["erros_graves"]) for r in res),
                legibilidade=round(sum(leg) / len(leg), 1) if leg else None,
                segundos_media=round(sum(r["segundos"] for r in res) / max(1, len(res)), 1))


def executar(casos: list[dict], fabricas: dict, configuracoes=CONFIGURACOES) -> dict:
    """fabricas: {config: callable(caso) -> dict}. Separado de main() para testar com fakes."""
    saida = {}
    for cfg in configuracoes:
        res = [fabricas[cfg](c) for c in casos]
        saida[cfg] = {"resumo": resumo(res), "casos": res}
    return saida


def markdown(modelo: str, r: dict) -> str:
    lin = [f"# Quatro configurações — LLM `{modelo}` — {date.today():%d/%m/%Y}", "",
           "| Configuração | Recusa correta | Fonte esperada citada | Frases | Erros graves (proxy) | Flesch | s/pergunta |",
           "|---|---|---|---:|---:|---:|---:|"]
    for cfg, x in r.items():
        s = x["resumo"]
        lin.append(f"| `{cfg}` | {s['recusa_correta']}/{s['n']} | {s['fonte_ok']}/{s['fonte_n']} | {s['frases']} | "
                   f"{s['erros_graves']} | {s['legibilidade'] or '—'} | {s['segundos_media']} |")
    lin += ["", "Erro grave (proxy): frase entregue sem trecho, com conselho, promessa ou número/prazo fora do trecho. "
            "Na configuração `llm` toda frase é \"sem fonte\" por construção. A contagem final de erros graves é da "
            "Cientista de dados e da Curadoria (issue #16)."]
    return "\n".join(lin) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--modelos", nargs="+", default=["qwen3:8b"])
    ap.add_argument("--configuracoes", nargs="+", default=list(CONFIGURACOES))
    ap.add_argument("--limite", type=int)
    a = ap.parse_args()
    from worker.evidencia.agentes.llm import ClienteOllama
    from worker.evidencia.agentes.montagem import montar

    casos = [json.loads(x) for x in PERGUNTAS.read_text(encoding="utf-8").splitlines() if x.strip()][: a.limite]
    for modelo in a.modelos:
        llm = ClienteOllama(modelo)
        sistemas = {}

        def fabrica(cfg, llm=llm, sistemas=sistemas, modelo=modelo):
            if cfg == "llm":
                return lambda c: rodar_llm(llm, c)
            if cfg not in sistemas:
                sistemas[cfg] = montar(modelo=modelo, reranker=cfg != "rag", nli=cfg == "rag_reranker_verificador")
            return lambda c: rodar_sistema(sistemas[cfg], c)

        r = executar(casos, {cfg: fabrica(cfg) for cfg in a.configuracoes}, a.configuracoes)
        destino = AQUI / "resultados" / f"{date.today():%Y-%m-%d}_{modelo.replace(':', '-')}"
        destino.parent.mkdir(exist_ok=True)
        destino.with_suffix(".json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
        destino.with_suffix(".md").write_text(markdown(modelo, r), encoding="utf-8")
        print(markdown(modelo, r))


if __name__ == "__main__":
    main()
