# ML Test Score — semana 1 (inicial) e semana 7 (final)

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


---

# Reavaliação final — semana 7 (issue #45)

Avaliado em 27/11/2026 sobre a branch `eng-ml/semanas-3-7` (semanas 3–7 + princípios de MLOps). Mesma rubrica e mesma regra (0 / 0,5 / 1; nota final = menor seção). Revisão do par (Cientista de dados) pendente.

## Dados

| # | S1 | S7 | Evidência |
|---|---:|---:|---|
| D1 Esquema das features | 0,5 | **1** | Esquemas Pandera (`treino/esquemas.py`) dos lotes, pares-ouro, perguntas, rascunho de intenção, log de previsões e referência de deriva; passo no CI e validação ao carregar o lote (o pipeline para) |
| D2 Toda feature é útil | 0 | 0 | Sem ablação |
| D3 Custo das features | 0 | 0 | — |
| D4 Requisitos (sem dado pessoal) | 0 | 0,5 | Extrator não devolve nome de parte (teste); log de previsões recusa campo com conteúdo do usuário (código e esquema); logs JSON mascaram CPF/CNPJ/e-mail/telefone. Falta o protocolo de anonimização do acervo (#1) |
| D5 Controles de privacidade no pipeline | 0,5 | **1** | Acima, automatizado no CI, mais o teste de resíduo de dado pessoal do recorte de jurisprudência |
| D6 Feature nova entra rápido | 0 | 0,5 | Estágio novo no `dvc.yaml` + `params.yaml` + linha no portão; manual |
| D7 Código de features testado | 1 | 1 | `tests/treino/`, `tests/modelos/`, `tests/worker/` no CI |
| **Seção** | **2,0** | **4,0** | |

## Desenvolvimento do modelo

| # | S1 | S7 | Evidência |
|---|---:|---:|---|
| M1 Especificação revisada e versionada | 0,5 | **1** | `params.yaml` + `dvc.yaml` (dvc.lock com o hash de código, dados e parâmetros de cada estágio), revisão por PR, CI |
| M2 Offline × online | 0 | 0 | Sem uso real |
| M3 Hiperparâmetros ajustados | 0,5 | 0,5 | Busca na validação (C do TF-IDF, limiares), manual |
| M4 Envelhecimento conhecido | 0 | 0 | — |
| M5 Modelo mais simples não é melhor | 0,5 | **1** | Todo relatório compara com majoritária/regras; a regra 0004 decidiu três vezes a favor das regras (resultado, intenção, ruído) e o portão acompanha os candidatos |
| M6 Qualidade nas fatias importantes | 0,5 | **1** | Erro grave por modelo (fase trocada, provido ↔ desprovido, contradição liberada, caso concreto tratado como informativo) no portão do CI, sem tolerância |
| M7 Inclusão | 0 | 0 | — |
| **Seção** | **2,0** | **3,5** | |

## Infraestrutura de ML

| # | S1 | S7 | Evidência |
|---|---:|---:|---|
| I1 Treino reproduzível | 0,5 | **1** | `dvc repro` refaz os relatórios com os mesmos números; segunda execução não refaz nada (dvc.lock); ambiente travado (`uv.lock` + `uv lock --check` no CI) |
| I2 Teste unitário da especificação | 1 | 1 | — |
| I3 Teste de integração do pipeline | 0 | **1** | `tests/worker/test_fluxo_documento.py` (PDF → fila → eventos, modelos falsos) no CI de PR; RQ + Redis + Postgres reais no `integracao.yml` |
| I4 Qualidade validada antes de servir | 0 | **1** | Portão de regressão (`treino/portao_regressao.py`) no CI e no pre-commit |
| I5 Depurável com um exemplo | 0 | 0,5 | `worker.documento.analisar(doc)` devolve segmentos, classificação, campos e frases de um documento; sem ferramenta dedicada |
| I6 Canário antes de servir | 0 | 0 | — |
| I7 Volta à versão anterior | 0 | **1** | Alias `em-uso`/`anterior` no MLflow, `treino/promover.py --rollback`, resolvido pelo worker (`registro.carregar_em_uso`); testado contra MLflow 3.18 e em `tests/modelos/test_promover.py` |
| **Seção** | **1,5** | **5,5** | |

## Monitoramento

| # | S1 | S7 | Evidência |
|---|---:|---:|---|
| Mo1 Mudança de dependência avisa | 0 | **1** | Dependabot (uv, Actions, npm, Docker) + `uv lock --check` |
| Mo2 Invariantes dos dados no uso | 0 | 0,5 | Esquema do log de previsões e relatório de deriva semanal; no CI roda sobre o log de exemplo, em produção precisa do cron do servidor |
| Mo3 Mesmas features no treino e no uso | 0 | **1** | Regras e pré-processamento vivem em `worker/modelos/` e o treino importa de lá (sem duplicação treino × serviço); a referência de deriva é calculada com o mesmo `worker.documento.analisar` |
| Mo4 Modelos não envelhecem demais | 0 | 0 | Revisões fixadas, sem alerta de idade |
| Mo5 Estabilidade numérica | 0 | 0 | — |
| Mo6 Desempenho computacional | 0,5 | 0,5 | Medição manual no M4; latência e memória ainda fora do CI |
| Mo7 Qualidade da previsão não regrediu | 0 | 0,5 | Deriva de confiança e taxa de abstenção (Evidently) com alerta; sem tráfego real |
| **Seção** | **0,5** | **3,5** | |

## Nota final

**3,5** (mínimo entre Dados 4,0 · Modelo 3,5 · Infraestrutura 5,5 · Monitoramento 3,5), contra 0,5 na semana 1. Na rubrica, 3–5 é "razoavelmente testado, mas ainda há mais a fazer".

Para subir, em ordem de custo × efeito: memória e latência no CI noturno do M4 (Mo6); deriva sobre o tráfego real com cron no servidor (Mo2, Mo7); idade da versão em uso no relatório semanal (Mo4); canário com sombra do candidato no worker (I6); ablação das features do segmentador (D2).
