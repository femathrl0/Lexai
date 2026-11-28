# 0012 — Hospedagem do deploy (opções; decisão do grupo)

Data: 27/11/2026 · Proposta: Felipe (Eng. de ML e MLOps) · **Status: aberta — o host ainda não foi escolhido.**

**Contexto.** O orçamento medido no M4 (`treino/relatorios/memoria_latencia_m4.md`) é o que manda: encoders (BGE-M3, reranker, NLI) ~7,4 GB no pico e a LLM `qwen3:8b` Q4 ~7,3 GB com `num_ctx` 16384. Na CPU, uma pergunta leva minutos (só a Validação fica ~7× mais lenta), então a LLM precisa de GPU ou de Apple Silicon. Para não travar a escolha, o deploy ficou **portátil**: imagens no GHCR (`imagens.yml`), `infra/docker-compose.prod.yml` com tudo em contêiner e a LLM atrás de `OLLAMA_HOST`, e um workflow de deploy por SSH desligado (`deploy.yml`, variável `DEPLOY_HABILITADO`).

| Opção | Como fica | Custo/limite | Quando escolher |
|---|---|---|---|
| **A. VPS sem GPU + LLM em host com GPU** | Compose prod na VPS (16 GB RAM, 4 vCPU); `OLLAMA_HOST` aponta para uma GPU alugada por hora ou para o Mac do grupo via túnel (Tailscale/WireGuard) | VPS ~R$ 150–250/mês; GPU só nas horas de demo | Recomendado para a demo e o teste com pessoas |
| B. Tudo num host com GPU NVIDIA (≥ 12 GB VRAM) | Compose prod + `--profile ollama` com `gpus: all`; encoders podem ir para `DISPOSITIVO=cuda` | Caro para ficar 24 h no ar | Se o teste com pessoas exigir latência baixa o tempo todo |
| C. Mac do grupo (M4) on-premises | Ollama e worker nativos (MPS); backend, Caddy, Postgres, Redis, MinIO e MLflow em contêiner; exposição por túnel | Sem custo; disponibilidade depende da máquina | Demo em sala; é o ambiente em que os números foram medidos |
| D. LLM por API hospedada | Troca `ClienteOllama` por um cliente de API | Pergunta e trechos saem do ambiente: exige revisão de privacidade (RNF01) e da Curadoria | Só com decisão explícita sobre dado pessoal |

**Decisão proposta.** **A** para o deploy da demo e do teste com pessoas, com **C** como contingência; **D** descartada por ora (dado pessoal).

**Pendências antes de qualquer opção ir ao ar.** Autenticação real (#19), persistência em `resultados` com retomada do SSE e checagem do dono da tarefa (#26), "apagar meus dados" e guarda com opt-in no MinIO (#33). Sem elas, o deploy serve só para a demo controlada, não para uso aberto.

### Registro da decisão (preencher)
- Data: ___ · Escolha: ___ · Responsável pelo host: ___
