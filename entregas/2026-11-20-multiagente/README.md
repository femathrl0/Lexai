# Entrega 20/11 — Primeiro protótipo multiagente

Enviar para a pasta da equipe no Teams, canal **4_Second Challenge**:

| Artefato | Onde está / como gerar | Responsável |
|---|---|---|
| Documentação (diagrama, responsabilidades, fluxo) | [`docs/agentes/arquitetura.md`](../../docs/agentes/arquitetura.md); exportar para PDF (abrir no GitHub ou VS Code e imprimir em PDF) | João + Mayara |
| Diagramas em PNG | [`docs/agentes/img/arquitetura.png`](../../docs/agentes/img/arquitetura.png) e [`sequencia.png`](../../docs/agentes/img/sequencia.png) (fontes `.mmd` ao lado; regerar com `npx @mermaid-js/mermaid-cli -i X.mmd -o X.png -b white -s 2 -w 1600`) | João (feito em 19/11) |
| Resultados da bateria | `avaliacao/agentes/resultados/*.md` — a de 17/11 (prompts v1) e a nova com os prompts v2, rodada no MacBook | Laisa (revisão) + Felipe (rodar) |
| Revisão jurídica da bateria de 17/11 | [`avaliacao/agentes/revisao_curadoria_2026-11-19.md`](../../avaliacao/agentes/revisao_curadoria_2026-11-19.md) | Laisa confirma |
| Recuperação sem LLM e calibração do NLI | `avaliacao/agentes/resultados/2026-11-19_recuperacao.md` e `2026-11-19_calibracao_nli.md` | Mayara + Felipe |
| Rastro de uma execução | `entregas/2026-11-20-multiagente/rastro_demo.json` (gerado pela CLI com `--rastro`) | Mayara |
| Vídeo da demo (2–3 min) | gravar a CLI com os 4 cenários do roteiro (seção 5 da documentação) | Felipe |

Antes de enviar: Laisa revisa as respostas da demo (revisão jurídica), e Davi confere que nenhum artefato contém dado pessoal.

## Antes de gravar a demo (MacBook M4)

```bash
uv sync --group worker && uv run --group treino dvc pull dados/processed
ollama pull qwen3:8b
uv run --group worker python -m avaliacao.agentes.checar_recuperacao        # 1–2 min, sem LLM
uv run --group worker python -m avaliacao.agentes.rodar_bateria --modelo qwen3:8b   # ~15 min; gera o .md da bateria v2
uv run --group worker python -m worker.evidencia.agentes.demo \
    "Quais verbas recebo na demissão sem justa causa e em quanto tempo?" --rastro entregas/2026-11-20-multiagente/rastro_demo.json
```

O recorte de jurisprudência (`corpus/jurisprudencia/recorte_demo.jsonl`) já está no Git e entra sozinho no buscador.
