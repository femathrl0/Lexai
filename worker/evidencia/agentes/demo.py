"""Demonstração do sistema multiagente.

    uv run --group worker python -m worker.evidencia.agentes.demo "Quais verbas recebo na demissão sem justa causa?"
    ... --persona advogado --buscador pgvector --modelo qwen3:8b --sem-nli --rastro dados/output/rastro.json
"""
from __future__ import annotations

import argparse
import json
import textwrap
from pathlib import Path

from .montagem import montar

CORES = {"orquestrador": "\033[90m", "triagem": "\033[35m", "pesquisa": "\033[34m", "analise": "\033[33m",
         "comunicacao": "\033[36m", "validacao": "\033[32m"}
FIM = "\033[0m"
NOMES = {"orquestrador": "Orquestrador", "triagem": "Triagem", "pesquisa": "Pesquisa", "analise": "Análise",
         "comunicacao": "Comunicação", "validacao": "Validação"}


def imprimir_mensagem(m) -> None:
    seta = {"pedido": "→", "resultado": "⇢", "devolucao": "↺", "aviso": "⚠"}[m.tipo]
    tempo = f" ({m.ms / 1000:.1f}s)" if m.ms else ""
    print(f"{CORES[m.de]}[{m.ordem:02d}] {NOMES[m.de]:>12} {seta} {NOMES[m.para]:<12}{FIM} {m.resumo}{tempo}")
    if m.motivo:
        print(textwrap.indent(textwrap.fill(f"motivo: {m.motivo}", 100), " " * 22))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pergunta")
    ap.add_argument("--persona", choices=["leigo", "advogado"], default="leigo")
    ap.add_argument("--buscador", choices=["local", "pgvector"], default="local")
    ap.add_argument("--modelo", help="modelo do Ollama (padrão: $LLM_MODELO ou qwen3:8b)")
    ap.add_argument("--jurisprudencia", help="JSONL com recorte de jurisprudência para o buscador local")
    ap.add_argument("--sem-nli", action="store_true", help="Validação só por regras (sem o cross-encoder NLI)")
    ap.add_argument("--sem-reranker", action="store_true")
    ap.add_argument("--rastro", type=Path, help="salva o rastro completo em JSON")
    a = ap.parse_args()

    print("Carregando agentes e modelos…")
    orq = montar(a.buscador, a.modelo, nli=not a.sem_nli, reranker=not a.sem_reranker, jurisprudencia=a.jurisprudencia,
                 ao_mensagem=imprimir_mensagem)
    print(f"\nPergunta: {a.pergunta}\nPúblico: {a.persona}\n\n— Diálogo entre os agentes —")
    estado = orq.responder(a.pergunta, persona=a.persona)

    por_id = {t.id: t for t in (estado.evidencias.trechos if estado.evidencias else [])}
    print("\n— Resposta —")
    for f in estado.resposta.frases:
        print(f"• {f.texto}\n    fonte: {f.fonte} — “{textwrap.shorten(por_id[f.trecho_id].texto, 160)}”")
    for aviso in estado.resposta.avisos:
        print(f"⚠ {aviso}")
    if a.rastro:
        a.rastro.parent.mkdir(parents=True, exist_ok=True)
        a.rastro.write_text(json.dumps(estado.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nRastro salvo em {a.rastro}")


if __name__ == "__main__":
    main()
