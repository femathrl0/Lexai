# avaliacao/ — Cientista de dados

| Pasta | Conteúdo |
|---|---|
| `dados/` | Perguntas e gabaritos herdados do lex_clt.ai (legislação: dev/teste aprovados e teste congelado; integração: casos de guardrails) |
| `casos_armadilha/` | Resultado ambíguo, prazo, aconselhamento disfarçado, foto ruim (desde a semana 2) |
| `pares_ouro/` | (pergunta, trecho, relevância 0–2) para o reranker; (frase, trecho, sustenta/contradiz/não trata) para o verificador |
| `regressao_juridica/` | Suíte de perguntas que roda em cada versão candidata do índice |
| `notebooks/` | Auditoria, EDA, chunking, recuperação e integração (herdados) |
| `scripts/` | Geração e juiz (Kaggle/local) herdados |
| `juiz.py` | LLM como juiz — só vale depois de validado contra a Curadoria |

O guia de anotação v1 e a taxonomia de rótulos são entregas da semana 1 (ver issues `cargo:cientista-dados`).
