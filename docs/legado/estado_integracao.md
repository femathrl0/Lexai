# Estado da integração (03_integracao)

Este é o documento de passagem para retomar o trabalho em outra sessão ou máquina. Atualizado em 2026-11-17.

## O que está pronto

| Etapa | Onde | Situação |
|---|---|---|
| Recuperação conjunta | `notebooks/03_integracao/01_recuperacao_conjunta.ipynb`, `src/integracao/recuperacao.py` | concluída |
| Guardrails de entrada e saída | `notebooks/03_integracao/02_guardrails.ipynb`, `src/integracao/guardrails.py` | concluída |
| Geração (Qwen3 8B no Kaggle) | `src/integracao/geracao.py`, `scripts/*geracao*`, `scripts/kaggle_gerar_respostas.py` | em execução no Kaggle |
| Juiz (Gemma 3 12B no Kaggle) | `src/integracao/juiz.py`, `scripts/*juiz*` | código pronto, ainda não executado |
| Notebooks 03 (geração) e 04 (avaliação) | — | a fazer |

## Resultados e decisões

### Recuperação

- **Configuração padrão** (`Configuracao()`):
  - busca semântica com BGE-M3 e busca lexical com pesos IDF, fundidas por RRF (k=60);
  - 10 candidatos por fonte e reranker `bge-reranker-v2-m3` com 256 tokens;
  - entrega com cotas: 3 artigos de legislação e 3 decisões.
- **Legislação** (16 perguntas): Hit@3 = 1,00, MRR = 0,93.
- **Jurisprudência** (17 perguntas): Hit@10 = 0,29, MRR = 0,13.
  - O gabarito é estreito; falta julgar a pertinência das decisões, o que o juiz vai fazer.
  - Ponto a investigar: sem reranker, a jurisprudência teve MRR = 0,21.
- **Tempo:** 15 a 21 s por pergunta na CPU.

### Guardrails

- **Classificação de entrada** (100 perguntas da curadoria):

  | Conjunto | Acurácia | Acerto em "segue para a busca ou não" |
  |---|---|---|
  | Ajuste | 0,80 | 0,96 |
  | Teste | 0,75 | 0,84 |

  - Fraquezas no teste: `institucional` acerta 0,45 e `orientar_sem_aconselhar` acerta 0,33.
- **Outros casos de entrada:** 4 de 4 perguntas negativas e 20 de 20 casos sintéticos corretos.
- **Saída:** concordância de 9 de 9 com a revisora. Essas 9 respostas foram usadas na calibração.
- **Regras acrescentadas depois do teste com o 8B:**
  - `consulta_individual_pede_dados`, que bloqueia a resposta;
  - `artigo_sem_fonte`, que só alerta.
- Números de processo das decisões entregues como fonte não são mascarados.

### Geração

- **Modelo:** `qwen3:8b-q8_0` no Ollama 0.40.16, na GPU T4 do Kaggle, sem modo de raciocínio.
- **Opções:** temperatura 0, semente 42, `num_ctx` de 16384 tokens (o maior prompt tem cerca de 10 mil).
- **Volume:** 137 perguntas da base.
  - 111 vão para a LLM: 99 `responder` e 12 `orientar_sem_aconselhar`.
  - 26 recebem resposta fixa, sem LLM: institucional, consulta individual, fora do escopo e outra jurisdição.
- **Prompt de sistema:** `SYSTEM_PROMPT_LEGAL` do grupo, sem alteração (`src/integracao/prompt_juridico.py`).

### Juiz

- **Modelo:** Gemma 3 12B no Kaggle. É gratuito e de outra família que o gerador.
- **Calibração:** antes de valer, o juiz é comparado com as 9 decisões da revisora, sem ver essas decisões.
- **Referências:** resposta-ouro da curadoria, ou pontos esperados e limites dos conjuntos aprovados.
- **Alternativa paga:** a classe `Juiz` chama a DeepSeek pela API, com a variável de ambiente `DEEPSEEK_API_KEY`.

## Próximos comandos

```powershell
# 1. Quando o kernel de geração terminar (status: kaggle kernels status laisapaiva93/lexia-geracao-qwen3)
.venv\Scripts\python.exe scripts\importar_geracao_kaggle.py
# Plano B, sem Kaggle: geração na GPU local com Q4
#   .venv\Scripts\python.exe scripts\gerar_respostas_local.py
#   .venv\Scripts\python.exe scripts\importar_geracao_kaggle.py --sem-download --local

# 2. Juiz
.venv\Scripts\python.exe scripts\preparar_juiz_kaggle.py
kaggle datasets create -p (Resolve-Path output\kaggle\juiz\dataset).Path
kaggle kernels push -p (Resolve-Path output\kaggle\juiz\kernel).Path
# Quando terminar:
.venv\Scripts\python.exe scripts\importar_juiz_kaggle.py
```

O passo 3 é criar os notebooks `03_geracao` e `04_avaliacao` a partir de `reports/integracao/geracao/` e `reports/integracao/juiz/`.

Use caminhos absolutos no `kaggle datasets create` e no `kaggle kernels push`. Com caminho relativo, o upload falha no Windows.

## Para retomar em outra máquina

Os itens abaixo não estão no GitHub e precisam ser recriados ou copiados.

- **PostgreSQL com pgvector (Docker):**
  - contêiner `lex-clt-postgres-1`, porta 15432, credenciais em `.env.pgvector.local`;
  - recriar o banco com os notebooks de indexação (legislação e jurisprudência 06), ou exportar o volume do Docker;
  - criar as visões lexicais com `Recuperador.preparar_lexico()`.
- **Modelos do Hugging Face** em cache local: `BAAI/bge-m3` (revisão `5617a9f`) e `BAAI/bge-reranker-v2-m3`.
- **Token do Kaggle** em `~/.kaggle`.
- **Pedidos e respostas** em `output/kaggle/geracao/` e `output/kaggle/juiz/`. Estão fora do Git porque contêm trechos de decisões e perguntas protegidas.
  - Os pedidos também estão no dataset privado `laisapaiva93/lexia-geracao-pedidos`.
- **Regra do repositório:** commits sem a linha de atribuição do Claude.
