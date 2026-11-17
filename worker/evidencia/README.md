# worker/evidencia — Eng. de IA

| Módulo | Origem (lex_clt.ai @ 9c3f43f) | Situação |
|---|---|---|
| `recuperador.py` | `src/integracao/recuperacao.py` | BGE-M3 + léxico IDF + RRF (k=60) + bge-reranker-v2-m3, cotas por fonte. Precisa migrar para o índice único `corpus_juridico` com `tipo_fonte` (decisão 0001). |
| `guardas.py` | `src/integracao/guardrails.py` | Guardas de entrada e saída por regras; falta o classificador de intenção (Eng. de ML). |
| `explicador.py` | `src/integracao/geracao.py` | Pedidos à LLM (Qwen3 8B) e respostas fixas; falta saída estruturada frase→trecho (`contratos.Explicacao`). |
| `prompts.py` | `src/integracao/prompt_juridico.py` | Agora lê `prompts/explicador/v1.md` e expõe `PROMPT_ID`/`PROMPT_SHA256`. |
| `indices/` | `src/storage/` | pgvector: importação, verificação e documentos-pai. |
| `verificador.py` | novo | stub — integra o NLI do Eng. de ML. |
