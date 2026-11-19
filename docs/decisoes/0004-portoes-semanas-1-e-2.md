# 0004 — Portões das semanas 1 e 2 (proposta para a reunião de Demo e portão)

Data: 19/11/2026 · Conduz: Felipe (Eng. de ML e MLOps), issues #7 e #14 · **Status: proposta; a decisão é do grupo na reunião.**

**Contexto.** O roteiro diz que a semana seguinte só começa com o portão aprovado ou com o desvio registrado aqui. Os portões das semanas 1 e 2 não foram decididos formalmente, e o grupo já está na entrega multiagente (20/11). Este registro junta a evidência de cada critério para a decisão não depender de memória. Números de recuperação de jurisprudência vêm do relatório herdado do lex_clt.ai (`dados/relatorios/integracao/recuperacao/resumo_metricas.csv`, 17 perguntas); os de legislação, desse relatório e do benchmark novo ([`treino/relatorios/benchmark_rerankers.md`](../../treino/relatorios/benchmark_rerankers.md)).

**Decisão proposta.**

*Semana 1 (#7) — critério: escopo, métricas e guia de anotação aprovados pelo grupo; entrevistas registradas.*

| Critério | Evidência | Situação |
|---|---|---|
| Escopo | `docs/manual.md` (produto, dentro e fora do escopo) | Atende |
| Métricas | Definições operacionais no manual (métricas e portões de qualidade); baselines e métrica por tarefa de ML em [0003](0003-baselines-por-tarefa.md) | Atende |
| Guia de anotação | Não está no repositório (#2) | **Pendente** |
| Entrevistas registradas | Não estão no repositório (#2) | **Pendente** |
| Entregas de ML (#3) | Baselines (0003), memória e latência no M4 e orçamento ([relatório](../../treino/relatorios/memoria_latencia_m4.md)), ML Test Score ([nota](../../treino/ml_test_score.md)), MLflow no Compose com experimentos | Atende |

Proposta: **aprovado com desvio**. Guia de anotação v1 e registro das entrevistas passam a ser pré-requisito do rótulo-ouro; sem eles o classificador segue em rótulo provisório e não pode ser promovido a `em-uso`.

*Semana 2 (#14) — critério: recall da busca híbrida com reranker medido por tipo de fonte e superior ao da busca só por palavra-chave; conjunto de teste congelado.*

| Fonte | Palavra-chave (hit@3 / hit@10) | Híbrida + reranker (hit@3 / hit@10) | Situação |
|---|---|---|---|
| Legislação (16 perguntas, herdado) | 0,00 / 0,13 | 1,00 / 1,00 | **Atende** |
| Jurisprudência (17 perguntas, herdado) | 0,12 / 0,24 | 0,12 / 0,18 | **Não atende**: empata no topo e perde em hit@10 |

| Critério | Evidência | Situação |
|---|---|---|
| Teste congelado — legislação | Hash `7d094eddf4d3…` reproduzido; portão `python -m treino.teste_congelado` no CI | Atende |
| Teste congelado — jurisprudência | Sem arquivo congelado no repositório | **Pendente** |
| Benchmark dos rerankers (#10) | [`benchmark_rerankers.md`](../../treino/relatorios/benchmark_rerankers.md), só legislação; pares-ouro graduados ainda não existem | Atende parcialmente |
| Baseline do classificador de tipo (#10) | [`classificador_tipo_baseline.md`](../../treino/relatorios/classificador_tipo_baseline.md), MLflow `classificador_tipo_fase` alias `candidato` | Atende (rótulo provisório) |

Proposta: **aprovado com desvio** para legislação; **reprovado** para jurisprudência até: (1) congelar um conjunto de teste de jurisprudência (Cientista de dados + Curadoria); (2) medir a híbrida + reranker nesse conjunto com o índice `corpus_juridico` (Eng. de IA), com a meta de superar a palavra-chave em hit@10; (3) pares-ouro de jurisprudência para o benchmark do reranker (Eng. de ML). Enquanto isso, a resposta não deve citar jurisprudência como fundamento principal.

**Alternativa descartada.** Dar os dois portões como aprovados porque a entrega multiagente já avançou: esconderia que a recuperação de jurisprudência não supera a palavra-chave, e esse é o tipo de fonte em que uma citação errada parece mais confiável para quem lê.

### Registro da reunião (preencher)

- Data: ___ · Presentes: ___
- Semana 1: [ ] Aprovado · [ ] Aprovado com desvio · [ ] Reprovado — observações: ___
- Semana 2: [ ] Aprovado · [ ] Aprovado com desvio · [ ] Reprovado — observações: ___
