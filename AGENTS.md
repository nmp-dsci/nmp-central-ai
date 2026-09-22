# AGENTS.md — nmp-central-ai

Read this first. `CLAUDE.md` is a pointer plus the rules that bite; the plan of record is
`ai_specs/s00_project_plan.md`; the outward contract is `PLATFORM.md`.

## What this is

The shared-services platform for `~/git/nmp-ai-portfolio`. Today: MLflow 3.16 on Postgres +
MinIO (S3 API) via Docker Compose, a project registry, an init script that owns experiment
ids, a verifier that proves each sibling can log, and agent context (portfolio-level
CLAUDE.md/AGENTS.md + a Claude Code plugin). M3 (2026-09-22): the same Postgres hosts one
database per sibling project, provisioned from the registry by `make db-init` and proved by
`make check`. Next: AWS demo (M2), LiteLLM gateway + metrics + MCP (M4), deploy modules +
template (M5).

## Decisions

| ID | Decision |
|---|---|
| D1 | Local MLflow on port 5000 (MLflow default). |
| D2 | Old per-project stores are not migrated: fresh start; archives stay read-only on disk. |
| D3 | M1 coupling is `MLFLOW_TRACKING_URI` only. A shared Python helper is a later option. |
| D4 | AWS demo = one Graviton EC2 (t4g.small) running this compose file + Caddy, with RDS + S3. ECS Express Mode is the upgrade path. App Runner is closed to new customers (2026-04-30). |
| D5 | RDS Postgres db.t4g.micro. |
| D6 | Repo `nmp-central-ai`, MIT, public. |
| D7 | Agent onboarding: portfolio-level CLAUDE.md/AGENTS.md importing PLATFORM.md (M0), plugin skills (M1), MCP server (M4). |
| D8 | MinIO image from quay.io (Docker Hub repo withdrawn), pinned; fallback RustFS. |
| D9 | Experiment naming `<project>/<purpose>` for new experiments; existing flat names kept in M1. |
| D10 | Server sets `MLFLOW_SERVER_ALLOWED_HOSTS` for `mlflow:5000`, `localhost`, `host.docker.internal`; otherwise in-network exporters get 403. |
| D11 | The server runs under uvicorn (MLflow default). `--gunicorn-opts` silently selects the Flask app, which has no `/v1/traces` route (404). Never add it back. |
| D13 | One database per project on the central cluster (`mlflow`, `dab`, `dataqa`); projects keep their schemas byte-for-byte. Not schema-per-project: data-qa already *is* four schemas with Alembic, dbt and RLS naming them. |
| D14 | Data moves by `pg_dump -Fc` → `pg_restore -j4 --no-owner`; the old container **and volume are deleted as soon as the central copy is verified** (unlike D2 — this data is easy to recreate). The dump in `backups/` is the safety net. |
| D15 | Role names are cluster-global. The registry declares every role and `db_init` refuses a duplicate; data-qa's generic `app_user`/`agent_ro`/`admin_ro` are grandfathered; new projects use `<project>_<purpose>`. |
| D16 | Projects use the cluster superuser `nmp` as their migration identity (user's call over per-database owner roles). Hence: sibling `reset` targets are schema-level inside their own database, never `DROP DATABASE`/`down -v`; back up first. Owner roles return if a project ever deploys to AWS (RDS has no superuser). |
| D17 | DataAgentBench's server flags adopted for the cluster, env-overridable: `shared_buffers=512MB work_mem=64MB maintenance_work_mem=512MB max_wal_size=4GB checkpoint_timeout=15min`. |
| D18 | A sibling's CI gets a throwaway `pgvector/pgvector:pg16` service container aliased `postgres` on the `nmp-central` network — same hostname as local, no platform checkout, no rule-zero breach. |
| D19 | No project databases in AWS: the AWS stack is a demo and only MLflow's store lives on RDS (M2). Registry `aws: false`; URL shapes stay identical so a later deploy is configuration. |
| D20 | A browser SQL frontend for the cluster is a ready-made tool, not ours: **DbGate Community** (`dbgate/dbgate`, pinned) as the compose service `dbgate`. Chosen over pgweb (read-only viewer, yearly releases), CloudBeaver (JVM, 3× the image, mandatory login), Adminer/pgAdmin (not editors / admin-oriented) after a trial against the live cluster (70→234 MB RAM). Investigation: `.lavish/s02_sql-frontend.html`. |
| D21 | Host port `5050` (validation mode `15050`, same +10 000 rule as D12). Not DbGate's default 3000, which collides with sibling dev servers. |
| D22 | The UI connects as the superuser `nmp` (D16), **one read-write connection per project database, fenced with `ALLOWED_DATABASES`**; `make db-init ARGS=--dbgate-readonly` flips every connection read-only. Connections are rendered from the registry into `.dbgate.env` (gitignored) — nobody types a host or password into the UI, and "add connection" is disabled by design. |
| D23 | No web login: the port is published on `127.0.0.1` only, like MLflow and the MinIO console. `LOGIN`/`PASSWORD` become necessary only if the bind is ever widened. |
| D24 | DbGate's built-in MCP server stays off; M4 decides the portfolio's MCP surface. |
| D12 | Validation never touches the live stack. Compose project names are machine-global, so a `make down` in CI or a no-mistakes worktree used to stop the live `nmp-central`. The Makefile switches to project/network `nmp-central-validate` on ports 15000/15432/19000/19001 whenever `CI`, `NO_MISTAKES_GATE` or `VALIDATION` is set or the checkout lives under `.no-mistakes/`; `make mode` shows which. Validation `down` also drops its volumes. |

## Layout

See README. The registry (`registry/projects.yaml`) is the source of truth for projects,
experiments, env-id variables, smoke commands and, since M3, each project's database (name,
roles, extensions, URL env vars, migrate and smoke commands); `scripts/_registry.py` is the
loader and refuses cluster-global name collisions.

## Runbooks

- Start / stop / reset: `make up`, `make down`, `make nuke` (asks), `make logs`.
- Bump the server: edit `services/mlflow/Dockerfile`, `make up`, `make mlflow-db-upgrade`.
- New project: `docs/onboarding.md`.
- Verify the platform end to end: `make check` (all) or `make check ARGS="--only P2"`.
- Databases: `make db-init` (idempotent, writes `.db-urls.env`), `make db-urls`, `make db-check`,
  `make db-backup DB=dab`, `make db-restore DB=dab FILE=backups/….dump`, `make db-psql DB=dab`.
  Moving a sibling's database in: `docs/runbooks/central-postgres.md`.
- OTLP ingest check without any sibling: `make otlp-smoke EXPERIMENT_ID=<id>`.

## Rules

- Never commit `.env`, `.mlflow-ids.env`, `.db-urls.env`, `backups/`, volumes, Terraform state or any real credential.
- Ports 5000 / 5432 / 9000 / 9001 are the platform's. Siblings must not squat them.
- Everything MLflow-related in the siblings is best-effort-silent (they swallow tracking
  errors). `make check` is the only way to know the platform works; run it after any change.
- `.lavish/` is tracked. Never add it to `.gitignore`.
- Public repo: account ids, SSO URLs and hostnames stay out of code and docs.
