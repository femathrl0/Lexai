# ML Test Score — semana 1 (inicial)

Rubrica de Breck et al., *The ML Test Score: A Rubric for ML Production Readiness and Technical Debt Reduction* (2017).
28 testes em 4 seções. Cada teste vale **0** (não feito), **0,5** (feito à mão, com resultado documentado) ou **1** (automatizado e rodando com frequência, no nosso caso no CI). A nota da seção é a soma; **a nota final é a menor das quatro seções**. Repetida na semana 7 (issue #45) para mostrar a evolução.

Avaliado em 19/11/2026 sobre a branch `eng-ml/semanas-1-2` · Responsável: Felipe (Eng. de ML e MLOps) · Revisão: Laisa (Cientista de dados).

## Dados

| # | Teste | Nota | Evidência / o que falta |
|---|---|---:|---|
| D1 | Expectativas sobre as features estão num esquema | 0,5 | Contratos Pydantic em `contratos/` testados no CI; falta esquema Pandera dos lotes (Eng. de dados) |
| D2 | Toda feature é útil | 0 | Sem ablação de features |
| D3 | Nenhuma feature custa mais do que vale | 0 | Sem medida de custo por feature |
| D4 | Features respeitam requisitos (sem dado pessoal) | 0 | Protocolo de anonimização ainda não existe (#1); o lote RepoJus já vem com partes em iniciais, mas nomes de advogados ficam no texto |
| D5 | Pipeline de dados com controles de privacidade | 0,5 | `dados/raw` fora do Git, DVC com remoto local; sem verificação automática |
| D6 | Feature nova entra rápido | 0 | — |
| D7 | Código de features tem teste | 1 | `tests/treino/test_classificador_tipo.py` (pré-processamento, mascaramento do cabeçalho, regras, correção de rótulo) roda no CI |
| | **Seção** | **2,0** | |

## Desenvolvimento do modelo

| # | Teste | Nota | Evidência / o que falta |
|---|---|---:|---|
| M1 | Especificação do modelo revisada e versionada | 0,5 | Scripts em `treino/`, revisão por PR; sem checagem automática |
| M2 | Métricas offline correlacionam com as online | 0 | Ainda não há uso real |
| M3 | Hiperparâmetros ajustados | 0,5 | `C` da regressão logística escolhido na validação; manual |
| M4 | Efeito do envelhecimento do modelo é conhecido | 0 | Mudança de jurisprudência e de formato do PJe não medida |
| M5 | Um modelo mais simples não é melhor | 0,5 | Comparação com classe majoritária e regras ([0004](../docs/decisoes/0004-baselines-por-tarefa.md)); manual |
| M6 | Qualidade suficiente nas fatias importantes | 0,5 | F1 por classe e troca de fase no relatório; sem portão |
| M7 | Modelo avaliado quanto à inclusão | 0 | — |
| | **Seção** | **2,0** | |

## Infraestrutura de ML

| # | Teste | Nota | Evidência / o que falta |
|---|---|---:|---|
| I1 | Treino reproduzível | 0,5 | Divisão por hash do processo, hash do lote e commit no MLflow; não rodado duas vezes no CI |
| I2 | Código da especificação do modelo tem teste unitário | 1 | `tests/treino/` no CI (métricas, regras, divisão, nDCG) |
| I3 | Pipeline completo tem teste de integração | 0 | — |
| I4 | Qualidade validada antes de servir | 0 | Portão de regressão de modelo ainda é TODO no `ci.yml` |
| I5 | Modelo depurável com um exemplo | 0 | — |
| I6 | Modelo passa por canário antes de servir | 0 | — |
| I7 | Modelo em uso pode voltar à versão anterior | 0 | Registro com alias `candidato` no MLflow existe; `worker/modelos/registro.py` ainda não lê `em-uso` |
| | **Seção** | **1,5** | |

## Monitoramento

| # | Teste | Nota | Evidência / o que falta |
|---|---|---:|---|
| Mo1 | Mudança de dependência avisa | 0 | — |
| Mo2 | Invariantes dos dados checadas no uso | 0 | — |
| Mo3 | Features iguais no treino e no uso | 0 | — |
| Mo4 | Modelos não envelhecem demais | 0 | — |
| Mo5 | Modelo numericamente estável | 0 | — |
| Mo6 | Desempenho computacional não regrediu | 0,5 | Memória e latência medidas à mão no M4 ([relatório](relatorios/memoria_latencia_m4.md)) |
| Mo7 | Qualidade da previsão não regrediu | 0 | Evidently ainda não configurado |
| | **Seção** | **0,5** | |

## Nota final

**0,5** (mínimo entre Dados 2,0 · Modelo 2,0 · Infraestrutura 1,5 · Monitoramento 0,5). É uma nota baixa e esperada na semana 1: na rubrica, 0–1 é "mais um projeto de pesquisa que um sistema em produção".

**Para subir até a semana 7**, em ordem de custo × efeito:
1. Portão de regressão de modelo no CI (I4) e teste de integração do pipeline com modelos falsos (I3).
2. `registro.carregar_em_uso()` lendo o alias `em-uso` do MLflow, com volta à versão anterior (I7).
3. Medida de memória e latência no CI noturno ou antes de cada demo (Mo6 → 1).
4. Relatório de deriva com Evidently sobre os documentos enviados (Mo2, Mo7).
5. Esquema Pandera dos lotes e protocolo de anonimização (D1, D4), com o Eng. de dados.
