# Migração do lex_clt.ai (commit 9c3f43f)

| Origem | Destino |
|---|---|
| `src/integracao/recuperacao.py` | `worker/evidencia/recuperador.py` |
| `src/integracao/guardrails.py` | `worker/evidencia/guardas.py` |
| `src/integracao/geracao.py` | `worker/evidencia/explicador.py` |
| `src/integracao/prompt_juridico.py` | `worker/evidencia/prompts.py` + texto em `prompts/explicador/v1.md` |
| `src/integracao/avaliacao_recuperacao.py` | `avaliacao/recuperacao.py` |
| `src/integracao/juiz.py` | `avaliacao/juiz.py` |
| `src/storage/*` | `worker/evidencia/indices/` |
| `src/jurisprudencia/*` | `worker/ingestao/jurisprudencia/` |
| `scripts/*` (dados) | `worker/ingestao/scripts/` |
| `scripts/*` (geração, juiz, Kaggle) | `avaliacao/scripts/` |
| `notebooks/*` | `avaliacao/notebooks/` |
| `data/evaluation/*` | `avaliacao/dados/` |
| `data/processed`, `data/chunks` | `dados/processed`, `dados/chunks` (DVC) |
| `reports/legislacao` | `dados/relatorios/legislacao` (DVC) |
| `reports/integracao` | `dados/relatorios/integracao` (Git) |
| `tests/*` | `tests/legado/` |
| `compose.pgvector.yaml` | `infra/docker-compose.yml` |
| `docs/*`, `requisitos.md` | `docs/legado/` |

Reescritas automáticas: imports `src.*` → novos módulos; caminhos `data/evaluation/` → `avaliacao/dados/`, `data/` → `dados/`, `reports/` → `dados/relatorios/`, `output/` → `dados/output/`; profundidade de `ROOT` nos scripts.

Atenção:
- Os manifestos de proveniência antigos registram hashes de código; como os imports mudaram, os hashes dos arquivos migrados não batem mais com os manifestos. Reexecutar a etapa gera manifestos novos.
- `data/raw/` (LawCodex e base de jurisprudência) não estava no Git do lex_clt.ai; recriar conforme `corpus/README_lawcodex.md` e `docs/legado/execucao_reproducao.md`.
- Os notebooks citam caminhos antigos nas saídas já gravadas; o código das células foi reescrito.
