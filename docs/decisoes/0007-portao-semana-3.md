# 0007 — Portão da semana 3: comparação LLM × RAG (proposta para a reunião)

Data: 27/11/2026 · Conduz: Felipe (Eng. de ML e MLOps), issue #21 · **Status: decidido em 27/11/2026 (sem reunião).**

**Contexto.** Critério: *configuração e LLM escolhidas com base em fidelidade, erros graves e recusa correta, com o relatório publicado e o ganho de cada cross-encoder medido.* A medição das quatro configurações (#18) depende do Ollama no M4; o runner ficou pronto (`avaliacao/configuracoes/rodar.py`, `make configuracoes MODELOS="qwen3:8b gemma3:4b"`), mas não rodou nesta máquina (sem GPU e sem Ollama).

| Critério | Evidência | Situação |
|---|---|---|
| Quatro configurações em 2–3 LLMs | Runner com testes; bateria do sistema completo com `qwen3:8b` em 24/11 (15/15 na Triagem, fonte esperada 10/11, 34/46 frases liberadas, 0 dado pessoal) | **Pendente**: rodar no M4 as quatro configurações |
| Ganho do reranker | nDCG@5 0,956 contra 0,950 do híbrido e 0,419 da palavra-chave ([benchmark](../../treino/relatorios/benchmark_rerankers.md)) | Atende (legislação) |
| Ganho do verificador | Validação completa: precisão 0,912 / recall 0,912 no limiar 0,55 (só o NLI: 0,816); 105 pares-ouro em rascunho ([calibração](../../avaliacao/agentes/resultados/2026-11-24_calibracao_nli_E_janela_lexical_20.md)) | Atende, com rótulos a aceitar |
| Benchmark de outros NLI | `treino/benchmark_nli.py` (baseline lexical + 3 candidatos, mesmo julgamento da Validação) | **Pendente**: na CPU leva horas por modelo; rodar no M4 (`make benchmark-nli DEVICE=mps`) |
| BERTimbau + LoRA × baseline | `treino/lora_tipo.py` com a regra da 0004 | **Pendente**: rodada completa no M4 (`make lora-tipo`) |
| Baselines do segmentador e do resultado | Segmentador sem títulos: TF-IDF + LR F1 0,92 × regra de posição 0,60 ([relatório](../../treino/relatorios/segmentador.md)); resultado do recurso: regras F1 0,982 / 1 troca grave × TF-IDF 0,977 / 5 ([relatório](../../treino/relatorios/resultado_pedido.md)) | Atende (rótulo prata) |
| Portão de regressão no CI | `treino/portao_regressao.py` no `ci.yml` | Atende |

**Decisão proposta.** **Aprovado com desvio**: configuração em uso = RAG + reranker + verificador com `qwen3:8b` Q4 (a única que cabe no orçamento de 16 GB, `treino/relatorios/memoria_latencia_m4.md`). O desvio registrado: falta o relatório das quatro configurações e do benchmark de NLI, a rodar no M4 antes da semana 6; até lá a escolha da LLM é por memória, não por fidelidade.

**Alternativa descartada.** Reprovar e segurar a semana 4 até o M4 rodar as quatro configurações: a semana 4 (fluxo do documento) não depende da escolha da LLM, e a configuração em uso já passa no portão do verificador.

### Registro da decisão

**Sem reunião de portão (orientação do grupo, 27/11/2026):** a decisão abaixo foi registrada pelo responsável pelos portões, Felipe (Eng. de ML e MLOps), com base na evidência desta página.

- Semana 3 (#21): **aprovado com desvio** — configuração em uso RAG + reranker + verificador com `qwen3:8b` Q4. Desvio: as quatro configurações, o benchmark de NLI e o BERTimbau + LoRA rodam no M4 (`make configuracoes`, `make benchmark-nli DEVICE=mps`, `make lora-tipo`); se o resultado mudar a escolha, esta decisão é revista.
