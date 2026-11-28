# Relatório de MLOps — Lexai (semanas 1–7)

Eng. de ML e MLOps: Felipe · issue #45 · 27/11/2026 · Revisão do par (Cientista de dados) pendente.

## 1. Ciclo de vida de um modelo

```
dados (RepoJus, pares-ouro, rascunhos)  ──► esquema Pandera (para o pipeline se falhar)
        │
params.yaml ──► dvc.yaml (dvc repro: só refaz o que mudou) ──► treino/relatorios/*.json  (+ run no MLflow)
        │                                                              │
        ▼                                                              ▼
registro MLflow: candidato ──► aprovado ──► em-uso   ◄── portão de regressão no CI (métrica principal + erro grave)
        (treino/promover.py; em-uso exige a Curadoria; alias "anterior" para rollback; docs/changelog_modelos.md)
        │
worker/modelos/registro.py: alias em-uso do MLflow, ou o fixado em worker/modelos/em_uso.yml (CI, offline)
        │
worker ──► log de previsões (só números) ──► deriva Evidently (semanal) ──► fila de aprendizado ativo (Label Studio)
```

## 2. O que existe, por prática

| Prática (manual, "MLOps nível 1") | Onde | Como verificar |
|---|---|---|
| Ambiente reproduzível | `uv.lock` versionado; torch CPU no Linux; `uv lock --check` no CI | `uv sync --frozen` |
| Pipeline reproduzível e incremental | `params.yaml`, `dvc.yaml`, `dvc.lock` | `make pipeline` duas vezes: a segunda não refaz nada |
| Validação de dados | `treino/esquemas.py` (Pandera) no CI e ao carregar o lote | `make esquemas` |
| Teste congelado | `treino/teste_congelado.py` (hash) no CI | — |
| Rastreamento de experimentos | MLflow em todo script (commit, hash dos dados, máquina, parâmetros, métricas); SQLite local se o servidor não estiver no ar | `make up` e `http://127.0.0.1:15000` |
| Baseline primeiro (0004) | Todo relatório traz majoritária/regras; candidatos só entram com +2 pontos e sem erro grave a mais | relatórios em `treino/relatorios/` |
| Registro com estágios e rollback | `treino/registrar_cross_encoders.py`, `treino/promover.py`, `worker/modelos/registro.py` | `tests/modelos/test_promover.py`, `test_registro.py` |
| Portões automáticos | regressão e erros graves (`treino/portao_regressao.py` + `treino/portoes/linha_base.json`), esquemas, contratos, tipos, testes com cobertura | `.github/workflows/ci.yml` |
| Teste de integração | fluxo do documento com modelos falsos (PR) e RQ + Redis + Postgres reais (noturno) | `integracao.yml`, `make test-integracao` |
| Monitoramento | `worker/modelos/monitoramento.py`, `treino/deriva.py`, `monitoramento.yml` | relatório HTML como artefato |
| Aprendizado ativo | `treino/aprendizado_ativo.py` | lote em `dados/output/aprendizado_ativo/` |
| Documentação | model cards (`docs/model-cards/`), decisões (`docs/decisoes/`), changelog de modelos | — |
| Privacidade | extrator sem nomes, log de previsões sem texto (código + esquema), logs JSON mascarados (`comum/log.py`) | `tests/test_log.py`, `tests/modelos/test_monitoramento.py` |
| Dependências | Dependabot | — |

## 3. Resultados do cargo (teste congelado)

Tabela consolidada em [`treino/relatorios/final.md`](../treino/relatorios/final.md). Em resumo: o que está em uso são **regras** em tipo, segmento, campos, resultado e intenção, e cross-encoders de terceiros com revisão fixa no reranker e no verificador. Em três de três comparações com rótulo prata, o modelo treinado não venceu as regras pela regra 0004 (resultado, intenção, ruído de OCR); onde não há título ou fórmula (segmentador sem títulos, foto com ruído), os modelos treinados são candidatos fortes.

## 4. Riscos e pendências

1. **Rótulos**: tudo é prata ou rascunho; nenhum modelo tem aprovação da Curadoria. É o principal bloqueio para qualquer `em-uso` treinado.
2. **Foto**: as regras não aguentam ruído de OCR (portão da semana 5 proposto como reprovado). Falta o conjunto de fotos do grupo.
3. **Rodadas no M4**: BERTimbau + LoRA, benchmark de NLI e as quatro configurações têm script e teste, mas não rodaram (esta máquina não tem GPU).
4. **Reprodutibilidade**: a rodada com o ambiente travado corrigiu a contagem de "fase trocada" do classificador de tipo (23 → 14), que dependia da versão do pandas. Por isso o `uv.lock` e o `dvc.lock` precisam andar juntos com qualquer número citado.
5. **ML Test Score**: 3,5 (semana 1: 0,5) — [detalhe](../treino/ml_test_score.md).
