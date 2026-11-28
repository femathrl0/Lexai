# Deploy

Runbook do deploy portátil. A escolha do host está aberta em [`decisoes/0012-hospedagem.md`](decisoes/0012-hospedagem.md).

## Peças

| Serviço | Imagem | Observação |
|---|---|---|
| caddy | `lexai-frontend` | SPA + proxy `/api` → backend, TLS automático (`DOMINIO`), SSE sem buffer |
| backend | `lexai-backend` | FastAPI; `/health` (vivo) e `/ready` (Redis, Postgres, nº de workers) |
| migrar | `lexai-backend` | `alembic upgrade head` a cada deploy, antes do backend |
| worker | `lexai-worker` | RQ; resolve os modelos em uso (MLflow ou `worker/modelos/em_uso.yml`); healthcheck por batimento no Redis |
| postgres / redis / minio | oficiais | Redis com senha e AOF; MinIO recebe a entrada do upload (o backend e o worker não dividem disco) |
| mlflow | `lexai-mlflow` | Postgres (banco `mlflow`) + MinIO (bucket `mlflow`); só em `127.0.0.1:15000` (acesso por túnel SSH) |
| ollama | oficial, profile `ollama` | Só quando a LLM roda no mesmo host; senão `OLLAMA_HOST` |

## Primeira vez no servidor

```bash
git clone https://github.com/femathrl0/Lexai /opt/lexai && cd /opt/lexai
cp .env.example .env.prod   # LEXAI_AMBIENTE=producao, DOMINIO=…, senhas fortes (a partida falha com as de exemplo)
docker compose -f infra/docker-compose.prod.yml --env-file .env.prod pull      # ou: build
docker compose -f infra/docker-compose.prod.yml --env-file .env.prod run --rm -e HF_HUB_OFFLINE=0 worker python -m worker.baixar_modelos
docker compose -f infra/docker-compose.prod.yml --env-file .env.prod up -d
curl -fsS https://$DOMINIO/api/ready
```

Modelos: os pesos das revisões fixadas vão para o volume `modelos` uma vez; depois o worker roda com `HF_HUB_OFFLINE=1`.
Para promover um modelo, `treino/promover.py` contra o MLflow do servidor (túnel `ssh -L 15000:127.0.0.1:15000`) e
reiniciar o worker (`docker compose … restart worker`): ele resolve o alias `em-uso` ao iniciar.

## Atualizar

Push na `main` gera as imagens (`imagens.yml`). Para subir: workflow **Deploy** (manual, com a tag) ou no servidor:
`./infra/scripts/backup.sh && LEXAI_TAG=<tag> docker compose -f infra/docker-compose.prod.yml --env-file .env.prod pull && … up -d`.
Voltar versão = subir a tag anterior; voltar modelo = `python -m treino.promover <modelo> --rollback`.

## Rotina

- **Backup**: `infra/scripts/backup.sh` no cron diário (`0 3 * * *`) e antes de todo deploy; guarda 14 dias. Testar a restauração uma vez por mês (comando no próprio script).
- **Deriva**: `docker compose … exec worker python -m treino.deriva relatorio` exige o grupo de treino; no servidor, copiar o volume `previsoes` e rodar `make deriva` numa máquina de desenvolvimento (semanal), ou agendar o workflow `monitoramento.yml` apontando para o log exportado.
- **Logs**: JSON em stdout (`docker compose … logs -f backend worker`), já mascarados; nunca logar pergunta ou trecho.

## Antes de abrir para o público

Bloqueios: autenticação (#19), resultados persistidos com retomada do SSE e dono da tarefa (#26), "apagar meus dados" e guarda com opt-in (#33), limite de requisições por IP no Caddy. Sem eles, use só em demo controlada.
