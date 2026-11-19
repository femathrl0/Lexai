# 0003 — Expansão de consulta, recorte de jurisprudência e limiar calibrado do NLI

Data: 19/11/2026

**Contexto.** A bateria de 17/11 (PR #55) mostrou três problemas: a Pesquisa não trazia o art. 477 da CLT para
"quais verbas recebo na demissão e em quanto tempo" (a pessoa fala "demissão" e "em quanto tempo"; a lei fala em
"extinção do contrato" e "prazo"); o buscador local não tinha jurisprudência, e a resposta à gestante saiu sem a
estabilidade; e o limiar de 0,5 do NLI era provisório, sem pares-ouro.

**Decisão.**
1. A Pesquisa acrescenta à consulta, antes da 1ª busca, os termos da lei equivalentes às palavras da pessoa, por um
   glossário de regras (`worker/evidencia/agentes/expansao.py`). Nunca remove palavras. A reformulação por LLM fica
   só para a nova busca pedida pela Validação.
2. O buscador local passa a carregar por padrão `corpus/jurisprudencia/recorte_demo.jsonl`: súmulas vigentes do TST
   e ementas anonimizadas do TRT-10, com o critério de anonimização "na dúvida, descarta a ementa".
3. Na Validação, antes do NLI, uma regra confere números e prazos: número com unidade na frase precisa estar no
   trecho. O limiar do NLI é o menor com precisão ≥ 0,90 nos pares-ouro do verificador
   (`avaliacao/agentes/calibrar_nli.py`); como nenhum chegou lá com o mDeBERTa na v1 dos pares, vale o de maior
   precisão, 0,75 (precisão 0,875, recall 0,62; em 0,5 eram 0,83 e 0,65).
5. O reranker julga, em artigo de lei longo, a janela de ~500 caracteres mais parecida com a consulta; súmula ou OJ
   com nota ≥ 0,5 toma a vaga da última ementa de caso concreto.

**Resultado sem LLM** (`avaliacao/agentes/resultados/2026-11-19_recuperacao.md`): 10 de 11 perguntas da bateria
trazem todas as fontes esperadas (8/11 sem a expansão); o art. 477 vem em 1º na demo_01.
4. Prompts de Análise e Comunicação v2 (regras para responder todas as partes da pergunta, não trocar responsável
   nem condição, regra de categoria só quando perguntada). A v1 continua no repositório e pode ser ligada por variável
   de ambiente para comparação.

**Alternativas descartadas.** Reformular toda pergunta com a LLM antes da busca: custa uma chamada a mais (~10 s no
M4), não é determinístico e não é revisável pela Curadoria. Subir a cota por fonte de 3 para 5: traz o art. 477, mas
dobra o contexto da Análise e o tempo da LLM. Manter 0,5 no NLI: sem medida, não dá para saber quantas frases falsas
passam nem quantas boas são barradas.
