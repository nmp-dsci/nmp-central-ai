# Runbook — the central Postgres (M3)

One cluster (`nmp-central-postgres-1`, pgvector/pg16, host port 5432, superuser `nmp`), one
database per project (D13). Everything below runs from `nmp-central-ai`. Decisions D13–D24 are in
`AGENTS.md`; the plans are `ai_specs/s02_m3_central_db.md` and `ai_specs/s04_db_ui.md`.

| Situation | Do |
|---|---|
| a project needs a database | add a `database:` block to `registry/projects.yaml` (name, roles, extensions, `env:`, `migrate`, `smoke`, `status: pending`), `make db-init`, `make db-urls`, paste the block into the project's `.env`, run its migrate command, set `status: migrated`, `make db-check ARGS="--only <ID>"` |
| which URL do I use? | `make db-urls`. Host side `localhost:5432`; from a compose stack on network `nmp-central`, host `postgres`. Never hardcode either. |
| `make db-init` says a role or database is declared twice | names are cluster-global (D15). Pick `<project>_<purpose>`; do not reuse another project's role. |
| a project's `reset` | drop and recreate **its own schemas inside its own database** as `nmp`. Never `DROP DATABASE`, never `down -v`. |
| back up one database | `make db-backup DB=dab` → `backups/dab-<utc>.dump` (gitignored) |
| restore | `make db-init` (database must exist) then `make db-restore DB=dab FILE=backups/dab-<utc>.dump` |
| psql | `make db-psql DB=dataqa` |
| browse / query in a browser | `make db-ui` → DbGate at `http://127.0.0.1:5050` (validation `15050`), one connection per project database as `nmp`, fenced to it (D20–D24). Connections come from `.dbgate.env`, which `make db-init` renders from the registry and reloads (DbGate reads it at start only). `make status` shows the connection count. Read-only: `make db-init ARGS=--dbgate-readonly`. Big schema: `ui_separate_schemas: true` on the database block. |
| server flags | `.env`: `PG_SHARED_BUFFERS`, `PG_WORK_MEM`, `PG_MAINTENANCE_WORK_MEM`, `PG_MAX_WAL_SIZE` (D17 defaults 512MB / 64MB / 512MB / 4GB); `make up` to apply |
| CI in a sibling | a service container `pgvector/pgvector:pg16` aliased `postgres` on the `nmp-central` network (D18); never the platform |

## Moving a project's existing Postgres in (the six steps, D14)

1. **Freeze.** Stop the project's app containers; leave its old `db` container running.
   `make db-init` here creates the empty target database, roles and extensions.
2. **Dump** from the old container: `make db-backup DB=<target> SRC=<old container> SRC_USER=<its superuser> SRC_DB=<its db> [SCHEMA=<one schema>]`.
   Check the size against `pg_database_size` in the old server.
3. **Restore**: `make db-restore DB=<target> FILE=backups/<target>-<utc>.dump [ROLE=<role>] [NO_PRIVS=1]` (`-j4 --no-owner`; GRANTs are restored because the registry created the roles first — data-qa's grants live in Alembic upgrades that will not re-run on an at-head database; pass `NO_PRIVS=1` only when the project's migrate command re-grants everything, as DataAgentBench's roles.sql does). A dump taken from a server whose superuser had another name carries `ALTER DEFAULT PRIVILEGES FOR ROLE <old superuser>` entries that cannot apply here: pass `SKIP="DEFAULT ACL"` and re-create them for `nmp` afterwards (data-qa: `ALTER DEFAULT PRIVILEGES IN SCHEMA app|raw|staging|marts GRANT SELECT ON TABLES TO admin_ro`, from its Alembic 0012). Without `ROLE` everything ends up owned by `nmp` (D16) — right for projects whose migrations ran as the superuser (data-qa). Pass `ROLE=<owner>` when the project's own role owned the schema and writes to it (DataAgentBench: `ROLE=dab_owner`), otherwise that role cannot create tables afterwards. Grants are re-applied by the project's migrate command.
4. **Prove.** Per-schema table counts and `pg_total_relation_size` within 2 % of the source; the project's `smoke` as every role (`make db-check ARGS="--only <ID>"`).
5. **Cut over.** Project URLs → `postgres:5432` / `localhost:5432`; delete its compose `db` service, volume and `depends_on` edges; join `nmp-central`; `make up` there and run its full smoke/e2e.
6. **Delete** the old container and its volume (`docker rm`, `docker volume rm`) — the dump from step 2 is the safety net. Confirm the port is free.

Rollback before step 6: put the old default back and `docker compose up db` in the project.
After step 6: `make db-restore` from the dump, or re-ingest from source.
