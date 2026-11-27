# 0010 — Portão da semana 6: integração completa (proposta para a reunião)

Data: 27/11/2026 · Conduz: Felipe, issue #42 · **Status: proposta; a decisão é do grupo.**

**Contexto.** Critério: *todos os portões do CI verdes; demo funcionando para as três personas (Ana, Rafael, Mariana).*

| Critério | Evidência | Situação |
|---|---|---|
| Portões do CI | Lint, tipos, contratos, esquema dos dados (Pandera), teste congelado, regressão de modelo e erros graves, testes com cobertura; integração (Postgres + Redis) noturna | Atende — falta o portão de fidelidade (revisão humana do juiz, #16) e o de isolamento por usuário (#26) |
| Model cards (#38) | [`docs/model-cards/`](../model-cards/README.md): todos os modelos em uso | Atende; aprovação da Curadoria pendente em todos |
| Aprendizado ativo (#38) | `treino/aprendizado_ativo.py`: lote do Label Studio com as previsões abaixo do limiar (36% no log de exemplo) | Atende |
| Demo para as três personas | CLI do multiagente (`python -m worker.evidencia.agentes.demo`) e fluxo do documento no worker; o app com RF01–RF08 é a #40 | **Pendente (#40)** |

**Decisão proposta.** **Aprovado com desvio** para a parte de ML e MLOps; **pendente** a demo das personas no app (#40). A versão da demo congela quando a #40 fechar, com nota de mudança e o `docs/changelog_modelos.md`.

### Registro da reunião (preencher)
- Data: ___ · Presentes: ___ · [ ] Aprovado · [ ] Aprovado com desvio · [ ] Reprovado — observações: ___
