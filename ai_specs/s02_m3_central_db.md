# s02 — M3: one Postgres for the portfolio (plan of record)

Status: decided and **built** 2026-09-22 · Review artifact: `.lavish/s01_m3-central-db-plan.html` · Receipt: `ai_specs/s03_m3_receipt.md`

## Goal

The central compose stack's Postgres 16 + pgvector server (`nmp-central-postgres-1`, host port
5432, superuser `nmp`) becomes the only database server on the machine. Every sibling that keeps
relational data gets its own database on that cluster, provisioned from `registry/projects.yaml`,
verified by `make check`, and moved over with its data intact.

## Survey (2026-09-22, verified against the repos and the Docker daemon)

| Project | Store today | Size | Verdict |
|---|---|---|---|
| DataAgentBench (P6) | pgvector/pg16, compose project `dab`, :5433, db `nmp`, schema `dataagentbench`, roles `dab_owner`/`dab_agent`, tuned flags | 6.6 GB, 2 813 tables | migrate |
| data-qa-agent (P5) | pgvector/pg16, service `db`, :5434, db `dataqa`, schemas `app raw staging marts`, ext `vector pgcrypto`, RLS, roles `app_user`/`agent_ro`/`admin_ro` (34 files), Alembic ×40, dbt | 2.3 GB | migrate |
| nmp-central-ai (MLflow) | the cluster, db `mlflow` | 83 MB | already central |
| floor-plan-reviewer | postgres:16-alpine, stopped since July | 49 MB | **retired** (no longer used); container + volume deleted in hygiene |
| ConvFinQA-agent | SQLite `.traces/traces.db` behind a server-free demo image | 58 MB | keep SQLite (deferred by decision) |
| value-invest-agent, productivity-tracker | DuckDB | small | out (different engine) |
| transcript-rag-agent | Neo4j | — | out (graph, single consumer) |
| v2v-prod-agent, Databricks projects | — | — | excluded (s00) |

## Decisions

| ID | Decision | Outcome |
|----|----------|---------|
| D13 | Layout | One database per project: `mlflow`, `dab`, `dataqa`. Projects keep their schemas byte-for-byte. |
| D14 | Data carry-over | `pg_dump -Fc` → `pg_restore -j4 --no-owner`; the old container **and volume are deleted as soon as the central copy is verified** (unlike D2 — this data is easy to recreate). The dump in `backups/` is the safety net. |
| D15 | Role namespace | Roles are cluster-global. data-qa's generic names are grandfathered; the registry declares every role and `db_init` refuses a duplicate; new projects use `<project>_<purpose>`. |
| D16 | Admin identity | Projects use the cluster superuser `nmp` for migrations (user's choice over a per-database owner). Consequence: every sibling `reset` is schema-level inside its own database, never `DROP DATABASE` / `down -v`; `make db-backup` before every playbook step. Owner roles return if a project ever deploys to AWS (RDS has no superuser). |
| D17 | Server flags | DAB's tuning adopted centrally, env-overridable: `shared_buffers=512MB work_mem=64MB maintenance_work_mem=512MB max_wal_size=4GB checkpoint_timeout=15min`. |
| D18 | Sibling CI | GitHub Actions service container `pgvector/pgvector:pg16` on the `nmp-central` network, alias `postgres`. |
| D19 | AWS | No project databases in AWS (demo only; MLflow's store on RDS per M2). Registry `aws: false`; dev = prod URL shapes kept so a later deploy is configuration. |

## Platform primitives (M3.0)

- `registry/projects.yaml`: `platform.postgres_uri` / `postgres_uri_compose`; per project a
  `database:` block `{name, roles, extensions, env: {VAR: role|superuser}, migrate, smoke, aws}`;
  a `PLATFORM` entry for the `mlflow` database so one script owns it all.
- `scripts/db_init.py`: renders idempotent SQL (roles with local password = role name,
  `<ROLE>_PASSWORD` overrides; databases; extensions per database), refuses duplicate role or
  database names across projects, applies it with `psql` inside the postgres container (or a
  superuser URL), writes `.db-urls.env` (gitignored).
- `scripts/check_databases.py`: per project connect as superuser and each role, check extensions,
  run the project's zero-LLM `smoke` with its URLs exported. Wired into `make check`.
- Make: `db-init`, `db-urls`, `db-check`, `db-backup DB=… [SRC=container]`, `db-restore DB=… FILE=…`.
- Compose: D17 flags; `services/postgres/init/01-mlflow.sh` retired in favour of `db-init`.
- `PLATFORM.md` Postgres table + rule 7; `AGENTS.md` D13–D19; plugin skill `platform-db` + eval;
  CI `stack` job runs `db-init` + `db-check --only PLATFORM`; `tests/test_db_init.py`.

## Migration playbooks (six steps each)

1 freeze writers · 2 `pg_dump -Fc` from the old container · 3 `pg_restore -j4 --no-owner` as `nmp`
· 4 prove (per-schema table counts and sizes within 2 %, project `db-smoke` as every role)
· 5 cut over (URLs → `postgres`/`localhost:5432`, compose `db` service deleted, network joined)
· 6 delete the old container and volume, port freed.

- **P6 DataAgentBench** (0.5 d): `config.py` defaults `:5433/nmp` → `:5432/dab` (incl.
  `pg_superuser_url` → `nmp`); `.env.example`; `infra/docker-compose.yml` deleted; Makefile
  `db-up` → `platform-up`, `db-roles`, `db-smoke`; AGENTS.md; registry P6 (MLflow + database).
- **P5 data-qa-agent** (1.5 d): compose `db` service + `depends_on` removed, hosts `db` → `postgres`,
  `ADMIN_DATABASE_URL` → `nmp:nmp@postgres:5432/dataqa`, migrate/pipeline join `nmp-central`;
  init SQL unchanged; dbt `DBT_HOST`/`DBT_USER` defaults; Makefile 5434 → 5432, `reset` schema-level;
  CI service container (D18); docs. Terraform/Bicep untouched.

## Verification

`make check` prints MLflow rows then Postgres rows (roles ok, extensions, smoke). Done when all
rows PASS with exactly one Postgres container running, 5433/5434 free, each migrated repo's CI
green, PLATFORM.md documents the contract, `platform-db` eval scores 1.00, receipt s03 written.

## Out of scope

ConvFinQA SQLite traces · DuckDB projects · Neo4j · v2v/Databricks · AWS databases · pooling.
