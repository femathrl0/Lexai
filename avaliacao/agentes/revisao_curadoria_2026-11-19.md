# Revisão das respostas da bateria de 17/11 (`qwen3:8b`) — rascunho para a Curadoria

**Feita em 19/11 como preparação da revisão jurídica (pendência do PR #55).** Cada frase liberada foi lida contra o
trecho citado e contra a pergunta. A palavra final sobre o que é erro jurídico continua sendo da Curadoria (Laisa):
ela confirma, corrige ou descarta cada linha antes da demo.

Legenda: ✅ correta e responde · ⚠️ imprecisa (muda o sentido ou omite condição) · ❌ incorreta · ➖ correta mas não
responde à pergunta (ruído).

## Frases liberadas (29)

| Pergunta | # | Fonte | Avaliação | Observação |
|---|---|---|---|---|
| q_test_01 | 1 | CLT, Art. 60 | ✅ | Exceção 12×36 correta. A regra principal (licença prévia) foi **removida** pelo NLI apesar de sustentada — ver calibração |
| q_test_02 | 1 | CLT, Art. 462 | ✅ | "intenção maliciosa" ≈ dolo. Faltou o caput (adiantamentos, lei, contrato coletivo) |
| q_test_03 | 1 | CLT, Art. 73 | ✅ | A frase dos 20% foi removida pelo NLI (p=0,32) mesmo sustentada |
| q_test_04 | 1 | CLT, Art. 391-A | ✅ | "durante o trabalho" simplifica "no curso do contrato"; aceitável para leigo |
| q_test_04 | 2 | CLT, Art. 391-A | ✅ | |
| q_test_04 | 3 | LC 150/2015, Art. 25 | ✅ | Regra do doméstico, dita como tal |
| q_test_06 | 1 | CLT, Art. 4º | ✅ | |
| q_test_06 | 2 | CLT, Art. 4º | ✅ | "usar instalações da empresa" aproxima "atividades particulares nas dependências" |
| q_test_07 | 1 | CLT, Art. 457 | ✅ | |
| q_test_07 | 2 | CLT, Art. 458 | ⚠️ | O artigo diz "compreende-se no **salário**"; a frase diz "remuneração" (conceitos distintos no art. 457) |
| q_test_07 | 3 | CLT, Art. 458 | ✅ | |
| q_test_07 | 4 | CLT, Art. 458 | ✅ | 25% e 20% conferem com o § 3º |
| q_test_08 | 1–6 | CLT, Art. 473 | ✅ | Incisos I a VI corretos. VII a X foram removidos pelo NLI apesar de sustentados; XI e XII não apareceram |
| demo_01 | 1 | CLT, Art. 147 | ➖ | Correta (férias do período incompleto), mas não é o centro da pergunta |
| demo_01 | 2 | Lei 7.998/1990, Art. 3º | ➖ | Correta; periférica |
| demo_01 | 3 | LC 150/2015, Art. 26 | ➖ | Regra do **doméstico** dada a quem não perguntou de doméstico. **Faltou o essencial: prazo de dez dias do art. 477, § 6º** |
| demo_02 | 1–2 | Lei 12.506/2011, Art. 1º | ✅ | 30 dias + 3 por ano, até 90 |
| arm_01 | 1 | CLT, Art. 394 | ❌ | O art. 394 faculta **romper o contrato** mediante **atestado médico**; "parar de trabalhar" muda o sentido e omite o atestado |
| arm_01 | 2 | Lei 8.213/1991, Art. 72 | ⚠️ | "A empresa tem que pagar o salário-maternidade" omite a **compensação** com a Previdência (§ 1º) e os casos pagos direto pela Previdência (§ 3º). Ponto apontado no PR |
| arm_01 | 3 | CLT, Art. 394-A | ⚠️ | "tarefas prejudiciais" generaliza "atividades insalubres" (graus e fases variam por inciso) |
| arm_01 | 4 | Lei 8.213/1991, Art. 72 | ➖ | Guarda de recibos por 10 anos: correto e irrelevante para a pergunta |
| arm_01 | — | — | ❌ (omissão) | **Faltou a estabilidade da gestante** (ADCT, art. 10, II, b; CLT, art. 391-A; Súmula 244 do TST). É o ponto central de "fui demitida grávida" |
| arm_03 | 1 | Lei 8.036/1990, Art. 12 | ➖ | Regra transitória de 1990 (centralização na CEF) — já cumprida; induz a erro sobre o presente |
| arm_03 | 2 | Lei 8.036/1990, Art. 12 | ➖ | Irrelevante. A pergunta (prazo do FGTS após a demissão) **ficou sem resposta**: faltaram art. 18 da Lei 8.036 e art. 477, § 6º, da CLT |

**Resumo:** 19 ✅ · 3 ⚠️ · 1 ❌ · 6 ➖ nas 29 frases liberadas, mais 2 omissões graves (estabilidade da gestante;
prazo das verbas/FGTS). Nenhuma frase deu ordem à pessoa e nenhum dado pessoal vazou (o CPF da arm_03 foi
mascarado na Triagem).

## Padrões de erro e o que foi mudado

| Padrão | Exemplos | Mudança em 19/11 | Onde |
|---|---|---|---|
| Busca não acha o artigo central quando a pergunta usa palavras do dia a dia | demo_01 (art. 477), arm_01 (391-A/ADCT), arm_03 (art. 18) | Expansão de consulta leigo → termos da lei antes da 1ª busca; jurisprudência (súmulas) no buscador local | `worker/evidencia/agentes/expansao.py`, `corpus/jurisprudencia/` |
| Regra de categoria (doméstico) usada como regra geral | demo_01 #3 | Prompt de Análise v2, regra 5 | `prompts/analise/v2.md` |
| Responsável ou condição simplificados | arm_01 #2, #1 | Análise v2 regra 7; Comunicação v2 regras 3–4 | `prompts/*/v2.md` |
| Parte da pergunta sem resposta, preenchida com outra regra | demo_01, arm_03 | Análise v2 regra 4 (uma frase por parte; diz quando falta fonte) | `prompts/analise/v2.md` |
| Caso concreto sem a regra central | arm_01 | Análise v2 regra 9 + Súmula 244 no recorte | `prompts/analise/v2.md` |
| NLI barra frases corretas (paráfrase leiga) | q_test_01, 03, 08 | Limiar calibrado nos pares-ouro | `avaliacao/agentes/resultados/*calibracao_nli*` |
| Dispositivo citado na frase diferente do trecho | arm_03 #2 ("art. 4º" para o § 4º do art. 12) | Análise v2 regra 6 | `prompts/analise/v2.md` |

**Efeito medido sem LLM** (`avaliacao/agentes/resultados/2026-11-19_recuperacao.md`): com as mudanças da Pesquisa,
10 de 11 perguntas trazem todas as fontes esperadas (8/11 sem a expansão). demo_01 traz o art. 477; arm_01 traz
art. 391-A, ADCT art. 10 e Súmula 244. A arm_03 ainda não traz o art. 477 (traz os arts. 18 e 20 da Lei 8.036).
O efeito nas frases só aparece na próxima bateria com LLM.

## O que a Curadoria precisa fazer

1. Confirmar ou corrigir as avaliações da tabela acima.
2. Aceitar os `pontos_esperados` novos de `demo_01`, `demo_02` e `arm_01`–`arm_04` em `avaliacao/agentes/perguntas_demo.jsonl` (marcados "aguarda aceite da Curadoria").
3. Aceitar os rótulos dos pares-ouro do verificador (`avaliacao/pares_ouro/verificador_v1.jsonl`), principalmente os marcados com `nota`.
4. Revisar a amostra da próxima bateria (rodada no MacBook com os prompts v2) antes da demo.
