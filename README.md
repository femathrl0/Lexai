# Lexai

Aplicação que ajuda trabalhadores a **compreender seus processos trabalhistas**: identifica o tipo de documento e a fase, explica a decisão em linguagem simples, mostra os possíveis próximos passos e fundamenta cada frase em um trecho do documento, da lei ou da jurisprudência — **sem substituir a orientação jurídica profissional**.

Toda decisão de arquitetura e processo está no [Manual de MLOps e arquitetura](docs/manual.md). Mudou a decisão? Muda o manual primeiro, depois o código.

## Princípios

1. **Explica, não aconselha.** Nunca diz o que a pessoa deve fazer.
2. **Toda frase tem origem** (RNF03).
3. **O que tem resposta certa é medido, não gerado.** A LLM só escreve a explicação.
4. **Nada vai ao usuário sem passar por um portão de qualidade.** O verificador é o último portão.
5. **Dado pessoal só fica com consentimento** (RNF01).

## Sistema multiagente (entrega 20/11)

Triagem → Pesquisa → Análise → Comunicação → Validação, coordenados por um Orquestrador. Documentação, diagramas e demo em [`docs/agentes/arquitetura.md`](docs/agentes/arquitetura.md).

```bash
uv run --group worker python -m worker.evidencia.agentes.demo "Quais verbas recebo na demissão sem justa causa?"
```

## Arquitetura em uma linha

`frontend (React)` → `backend (FastAPI)` → `Redis (filas perguntas > documentos > ingestao_juridica)` → `worker (único que carrega modelos)` → `PostgreSQL + pgvector (corpus_juridico, trechos_usuario)`; apoio: `MinIO` (originais com opt-in) e `MLflow` (registro de modelos).

## Cargos

| Cargo | Titular | Par (revisa e cobre) | Issues |
|---|---|---|---|
| 1. Eng. de dados | Davi ([@Withy-S](https://github.com/Withy-S)) | Felipe (Eng. de ML e MLOps) | [`cargo:eng-dados`](../../issues?q=label%3Acargo%3Aeng-dados) |
| 2. Cientista de dados | Laisa ([@paiva-l](https://github.com/paiva-l)) | Mayara (Eng. de IA) | [`cargo:cientista-dados`](../../issues?q=label%3Acargo%3Acientista-dados) |
| 3. Eng. de ML e MLOps | Felipe ([@femathrl0](https://github.com/femathrl0)) | Laisa (Cientista de dados) | [`cargo:eng-ml`](../../issues?q=label%3Acargo%3Aeng-ml) |
| 4. Eng. de IA (LLM e RAG) | Mayara ([@MayaraVieiraa](https://github.com/MayaraVieiraa)) | João (Eng. de software) | [`cargo:eng-ia`](../../issues?q=label%3Acargo%3Aeng-ia) |
| 5. Eng. de software | João ([@joaomarcosmelo2023](https://github.com/joaomarcosmelo2023)) | Davi (Eng. de dados) | [`cargo:eng-software`](../../issues?q=label%3Acargo%3Aeng-software) |
| Curadoria jurídica | Laisa ([@paiva-l](https://github.com/paiva-l)) | — | [`curadoria`](../../issues?q=label%3Acuradoria) |

> Os portões semanais ficam com o Felipe. Primeiro PR de cada pessoa: um ajuste pequeno no README, para testar o fluxo de revisão com o par.

## Primeiro dia

```bash
# 1. ferramentas: uv, Docker, Ollama, Node 22
curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. ambiente
cp .env.example .env            # troque as senhas
make setup                      # uv sync (backend + dev)
make up                         # Postgres+pgvector, Redis, MLflow, MinIO
make migrar                     # alembic upgrade head
make test                       # tudo verde = ambiente certo
# 3. modelos (LLM quantizada, embeddings, cross-encoders) e memória livre
make preparar-modelos
# 4. dados versionados (pasta compartilhada do DVC; ajuste a url em .dvc/config se preciso)
uv run --group treino dvc pull
# 5. rodar
make backend   # http://127.0.0.1:8000/docs
make worker    # nativo no macOS, fora do Docker (GPU do M4)
make frontend  # http://127.0.0.1:5173
```

Depois: ler o [guia de anotação](avaliacao/README.md) e anotar dez documentos; combinar com o par um horário fixo de revisão.

## Como o trabalho anda

- Toda tarefa nasce de um entregável da semana e vira issue (milestone `Semana N`, label do cargo e do requisito).
- **PR pequeno**, uma branch por tarefa; o par revisa em até um dia útil; CI verde + aprovação = entra.
- **Contrato muda em PR próprio**, aprovado por quem produz e por quem consome.
- **Modelo, prompt e índice mudam pelo ciclo de MLOps**: versão candidata → portões no CI → Curadoria. Ninguém troca à mão o que está "em uso".
- **Revisão jurídica** tem fila própria: label `revisao-juridica`, com rascunho e fonte.
- **Decisão nova** vai para [`docs/decisoes/`](docs/decisoes/) antes do código.

## Onde fica cada coisa

| Pasta | O que guarda | Dono |
|---|---|---|
| `frontend/` | App React + TypeScript (Vite) | Eng. de software |
| `backend/` | API FastAPI, autenticação, consentimento, SSE — **sem bibliotecas de ML** | Eng. de software |
| `contratos/` | Contratos Pydantic entre módulos e eventos SSE | Eng. de software, com aprovação dos dois lados |
| `worker/leitura/` | Leitor e segmentador por regras | Eng. de dados |
| `worker/modelos/` | Carregamento e inferência dos classificadores, reranker e verificador | Eng. de ML |
| `worker/evidencia/` | Recuperador, explicador, guardas, encadeamento | Eng. de IA |
| `worker/ingestao/` | Ingestão jurídica (divisão estrutural, embeddings, publicação) | Eng. de dados + Eng. de IA |
| `treino/` | Scripts de treino, sempre rastreados no MLflow | Eng. de ML |
| `avaliacao/` | Suíte de avaliação, casos armadilha, pares-ouro, regressão jurídica, notebooks | Cientista de dados |
| `dados/` | Ponteiros do DVC; nunca dados crus no Git | Eng. de dados |
| `corpus/` | Manifesto das fontes jurídicas versionadas | Eng. de IA + Curadoria |
| `prompts/` | Prompts versionados | Eng. de IA |
| `infra/` | Docker Compose e migrações do banco | Eng. de software |
| `docs/` | Manual, decisões, model cards, datasheet, documentos herdados | Todos |

## Origem

Este repositório reorganiza, no layout do manual, o trabalho das semanas 1–3 feito em [`paiva-l/lex_clt.ai`](https://github.com/paiva-l/lex_clt.ai) (commit `9c3f43f`): RAG de legislação (25 normas, 5.284 artigos, BGE-M3 + léxico + RRF + bge-reranker-v2-m3, Recall@3 = 1,00 no dev), pipeline de jurisprudência, guardrails, geração com Qwen3 8B e juiz. Os documentos originais estão em [`docs/legado/`](docs/legado/); o mapa de migração está em [`docs/legado/MIGRACAO.md`](docs/legado/MIGRACAO.md).

> O app explica o que o documento diz; não substitui advogado, Defensoria Pública ou o setor de atermação.

## MLOps e deploy

- **Pipeline de ML:** `make pipeline` (DVC: só refaz o que mudou), `make portao-regressao`, `make esquemas`; parâmetros em `params.yaml`; relatórios em `treino/relatorios/`; consolidado em `treino/relatorios/final.md`.
- **Modelos em uso:** `worker/modelos/em_uso.yml` (ou o alias `em-uso` no MLflow); promoção e rollback com `treino/promover.py`; cards em `docs/model-cards/`.
- **Relatório de MLOps:** [`docs/relatorio_mlops.md`](docs/relatorio_mlops.md) · ML Test Score: [`treino/ml_test_score.md`](treino/ml_test_score.md).
- **Deploy:** [`docs/deploy.md`](docs/deploy.md) (`infra/docker-compose.prod.yml`, imagens no GHCR); hospedagem em aberto na [decisão 0012](docs/decisoes/0012-hospedagem.md).
