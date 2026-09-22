#!/bin/bash
# Runs once on first start of an EMPTY postgres volume: create the mlflow role + database so the
# mlflow service can boot before anyone runs `make db-init`. Everything else (project databases,
# roles, extensions) is `make db-init` from registry/projects.yaml, which is idempotent and also
# re-asserts this role and database on an existing volume (M3, D13-D16).
set -euo pipefail
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    DO \$\$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${MLFLOW_DB_USER}') THEN
        CREATE ROLE ${MLFLOW_DB_USER} LOGIN PASSWORD '${MLFLOW_DB_PASSWORD}';
      END IF;
    END
    \$\$;
EOSQL
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -tc \
  "SELECT 1 FROM pg_database WHERE datname = 'mlflow'" | grep -q 1 || \
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    -c "CREATE DATABASE mlflow OWNER ${MLFLOW_DB_USER}"
echo "mlflow role and database ready"
