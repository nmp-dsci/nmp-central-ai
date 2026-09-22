---
name: platform-db
description: Use the central nmp-central-ai Postgres from any nmp-ai-portfolio project. Use when asked to add a table, schema, migration, database, role or extension; to connect to Postgres, reset or seed a database, run Alembic or dbt, back up or restore data; or when code touches DATABASE_URL, a postgresql:// URL, docker-compose db/postgres services, pgvector or psql.
---

# platform-db

The portfolio has ONE Postgres server and every project has ONE database on it (D13).
Contract: `~/git/nmp-ai-portfolio/nmp-central-ai/PLATFORM.md` (Postgres table, rule 7).
Runbook: `nmp-central-ai/docs/runbooks/central-postgres.md`.

## Facts

- Host side: `localhost:5432`. From a compose stack on network `nmp-central`: host `postgres`, port 5432.
- Server: Postgres 16 + pgvector (`pgvector/pgvector:pg16`), superuser `nmp` (D16).
- Databases: `mlflow` (platform), `dab` (DataAgentBench), `dataqa` (data-qa-agent). A new project gets its own.
- Roles are cluster-global and registry-owned (D15): declared in `nmp-central-ai/registry/projects.yaml`,
  created by `make db-init`, duplicates refused. New roles are `<project>_<purpose>`. Local password = role name.
- URLs come from `make -C ~/git/nmp-ai-portfolio/nmp-central-ai db-urls` (one block per project, paste into
  the project's `.env`). Never hardcode a URL or a port.
- Extensions (vector, pgcrypto, …) are declared in the registry and created by `db-init`; project SQL never needs `CREATE EXTENSION` to succeed, `IF NOT EXISTS` is fine.
- Migrations run as `nmp` inside the project's own database (Alembic, dbt, `roles.sql`, `create_all` — whatever the project already uses).
- A browser UI exists for the human: `make -C ~/git/nmp-ai-portfolio/nmp-central-ai db-ui` (DbGate, `http://127.0.0.1:5050`, one connection per database as `nmp`). Point the user at it when they want to *look* at data; you keep using psql / the project's URL, never the UI.

## Do this

1. Before any database work: `make -C ~/git/nmp-ai-portfolio/nmp-central-ai status` (starts nothing; says DOWN → `... up`). Then `make -C ~/git/nmp-ai-portfolio/nmp-central-ai db-check ARGS="--only <ID>"` to see the project's row.
2. Adding a table/column: write it in the project's existing migration tool against the project's `DATABASE_URL`/`ADMIN_DATABASE_URL` from `.env`. Do not create a compose `db` service, do not change the port, do not invent a new database.
3. A project with no database yet: add a `database:` block to `registry/projects.yaml` (name, roles, extensions, `env:` mapping VAR → role|superuser, `migrate`, a zero-LLM `smoke`, `status: pending`), `make db-init`, paste the block from `make db-urls`, run the migrate command, set `status: migrated`, `make db-check ARGS="--only <ID>"`.
4. Reset/seed: drop and recreate the project's **own schemas** inside its **own database** as `nmp`, then re-run its migrate + seed. Never `DROP DATABASE`, never `docker compose down -v`, never touch another project's database.
5. Before anything destructive: `make -C ~/git/nmp-ai-portfolio/nmp-central-ai db-backup DB=<db>`.
6. CI: a throwaway `pgvector/pgvector:pg16` service container aliased `postgres` on the `nmp-central` network (D18) — never the platform, never a `db` service in the project compose file.
7. AWS: no project databases in AWS (D19). Keep the URL shape identical so a future deploy is configuration.

## Never

- Add a `postgres`/`db` service to a project's docker-compose, or bind another host port (5433/5434 are gone).
- Hardcode `localhost:5433`, `:5434`, a database URL, a password, or a role another project owns.
- `DROP DATABASE`, `down -v`, or connect as `nmp` to a database that is not the project's.
- Put customer data or secrets in seed files or dumps that get committed; `backups/` is gitignored.
