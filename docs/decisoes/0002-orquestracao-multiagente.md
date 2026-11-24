# 0002 — Orquestração multiagente própria, com o verificador como último portão

Data: 17/11/2026

**Contexto.** A entrega de 20/11 pede um sistema com no mínimo dois agentes especializados, com responsabilidades claras e boa qualidade de interação. O manual já previa o pipeline de evidência (guardas, recuperador, reranker, explicador, verificador) como "pipeline próprio dentro do worker, com estado explícito e contratos tipados", deixando frameworks de agentes para quando o fluxo crescer.

**Decisão.** Cinco agentes (Triagem, Pesquisa, Análise, Comunicação, Validação) e um Orquestrador próprio em `worker/evidencia/agentes/`. Os agentes trocam `Mensagem` tipadas (`contratos/agentes.py`) registradas num rastro. A Comunicação simplifica antes da Validação, para que a simplificação também seja verificada. A Validação pode devolver trabalho uma vez à Análise (refazer frases) e uma vez à Pesquisa (nova busca); depois remove o que segue reprovado e emite aviso. O mesmo orquestrador roda na CLI de demonstração e no worker (`responder_pergunta`).

**Alternativa descartada.** LangGraph ou CrewAI: mais peças para instalar e explicar em três dias. Com um laço livre entre agentes LLM, não há como garantir término nem que nenhuma frase saia sem passar pelo verificador.
