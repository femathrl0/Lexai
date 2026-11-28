#!/usr/bin/env bash
# Backup do Postgres (dados do app + MLflow) antes de cada deploy e no cron diário. Guarda os 14 mais recentes.
#   ./infra/scripts/backup.sh            # → backups/AAAA-MM-DD_HHMM_{lexai,mlflow}.sql.gz
# Restauração: gunzip -c backups/<arquivo>.sql.gz | docker compose -f infra/docker-compose.prod.yml exec -T postgres psql -U lexai -d <banco>
set -euo pipefail
cd "$(dirname "$0")/../.."
COMPOSE="docker compose -f infra/docker-compose.prod.yml --env-file ${ENV_FILE:-.env.prod}"
USUARIO="${POSTGRES_USER:-lexai}"
mkdir -p backups
quando=$(date +%Y-%m-%d_%H%M)
for banco in "${POSTGRES_DB:-lexai}" mlflow; do
  if $COMPOSE exec -T postgres psql -U "$USUARIO" -lqt | cut -d'|' -f1 | grep -qw "$banco"; then
    $COMPOSE exec -T postgres pg_dump -U "$USUARIO" -d "$banco" --no-owner | gzip > "backups/${quando}_${banco}.sql.gz"
    echo "backup: backups/${quando}_${banco}.sql.gz"
  fi
done
ls -1t backups/*.sql.gz 2>/dev/null | tail -n +29 | xargs -r rm --
