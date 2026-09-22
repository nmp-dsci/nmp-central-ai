# nmp-central-ai — platform contract

Shared services for every project in `~/git/nmp-ai-portfolio`. This file is the
contract an agent or a person needs to use them. It is imported into every
sibling's context by the portfolio-level `CLAUDE.md` / `AGENTS.md`.

**Rule zero: never start your own MLflow, Postgres, MinIO or gateway inside a
project. Use these.**

## Status

```bash
make -C ~/git/nmp-ai-portfolio/nmp-central-ai status   # health; `up` starts it
```

## MLflow — tracking · traces · prompt registry · model registry

| | value |
|---|---|
| URL from the host | `http://localhost:5000` |
| URL from a sibling's compose stack | `http://mlflow:5000` after joining the external network `nmp-central` |
| OTLP traces | `POST <url>/v1/traces` with header `x-mlflow-experiment-id: <id>` |
| The one env var | `MLFLOW_TRACKING_URI` (every project honours it; nothing else couples you) |
| Server version | 3.16.x, pinned in `services/mlflow/Dockerfile`; clients need `mlflow>=3.12,<4` |
| Backend | Postgres (`postgres:5432`, db `mlflow`) + S3-API artifacts (`s3://mlflow-artifacts` on MinIO); the server proxies artifacts, so clients need no S3 credentials |
| Experiment naming | `<project>/<purpose>` for new experiments (e.g. `data-qa/evals`). Existing flat names (`convfinqa`, `dabstep-loop`, `tau2-loop`) are kept as-is. |
| Required run tags | `project`, `git_sha`, `env` (`local` \| `aws`), `billing` where relevant |
| Experiment ids | `make mlflow-init` here prints them and writes `.mlflow-ids.env`. **Never hardcode an id.** |
| Registry | `registry/projects.yaml` is the source of truth for who uses what |

## Rules for agents working in a sibling project

1. If the server is unreachable, say so and run `make -C ~/git/nmp-ai-portfolio/nmp-central-ai up`.
   Do **not** fall back to a local `sqlite:` or `file:` store; do not change the port.
2. Do not create, rename or delete experiments, registered models or prompts that belong to
   another project. The registry lists every name.
3. Never log secrets, API keys, raw customer data or PII into runs, params, tags or traces.
4. Keep trace volume sane: keep span trimming on, do not set `MLFLOW_TRACE_FULL=1` on shared runs.
5. Onboarding a new project: add it to `registry/projects.yaml`, run `make mlflow-init`, set the
   project's default tracking URI to the central one, add a zero-cost `smoke` command, run
   `make check ARGS="--only <ID>"`. Full steps: `docs/onboarding.md`.
6. Skills: install the `nmp-platform` plugin once (`/plugin marketplace add ~/git/nmp-ai-portfolio/nmp-central-ai`,
   then `/plugin install nmp-platform@nmp-central-ai`). It carries `platform-mlflow`, `platform-db` and `platform-onboard`.

## Postgres — one database per project (M3)

| | value |
|---|---|
| Host from the host | `localhost:5432` |
| Host from a sibling's compose stack | `postgres:5432` after joining the external network `nmp-central` |
| Server | Postgres 16 + pgvector (`pgvector/pgvector:pg16`), tuned flags (D17) |
| Layout | **one database per project** (D13): `mlflow`, `dab`, `dataqa`. Your schemas, tables, grants and RLS live inside your database and stay yours. |
| Roles | cluster-global, so declared in `registry/projects.yaml` and created by `make db-init`; a duplicate is refused (D15). New roles are `<project>_<purpose>`. Local password = role name (or a grandfathered per-role default); `<ROLE>_PASSWORD` overrides. |
| Admin identity | the cluster superuser `nmp` (D16), for your migrations only and only inside your own database |
| Extensions | declared in the registry, created by `db-init` before any project SQL runs |
| URLs | `make db-init` writes `.db-urls.env` — one block per project; paste your block into your `.env`. **Never hardcode a URL, never hardcode a port.** |
| Backups | `make db-backup DB=<db>` → `backups/`, `make db-restore DB=<db> FILE=…` |
| Verify | `make check` (or `make db-check ARGS="--only <ID>"`) connects as every role and runs your zero-LLM `smoke` |
| AWS | no project databases in AWS (D19). Keep the URL shape so a future deploy is configuration only. |

## Rule 7 for databases

7. Never add a `postgres`/`db` service to a project's compose file; never `DROP DATABASE`; never
   `docker compose down -v` a stack that used to own a database. A project's `reset` drops and
   recreates **its own schemas inside its own database** as `nmp`, nothing wider. Back up first:
   `make -C ~/git/nmp-ai-portfolio/nmp-central-ai db-backup DB=<db>`. In CI, use a throwaway
   service container `pgvector/pgvector:pg16` aliased `postgres` on the `nmp-central` network (D18).

## Coming (not yet available)

- M2: the same stack on AWS (one Graviton EC2 + RDS + S3), URL in `.env` as `MLFLOW_TRACKING_URI_AWS`.
- M4: LiteLLM gateway with per-project keys and budgets; Prometheus + Grafana; an MCP server.

Runbooks: `docs/runbooks/`. Plans of record: `ai_specs/s00_project_plan.md` (platform), `ai_specs/s02_m3_central_db.md` (databases).
