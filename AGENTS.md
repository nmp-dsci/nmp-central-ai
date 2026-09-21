# AGENTS.md — nmp-central-ai

Read this first. `CLAUDE.md` is a pointer plus the rules that bite; the plan of record is
`ai_specs/s00_project_plan.md`; the outward contract is `PLATFORM.md`.

## What this is

The shared-services platform for `~/git/nmp-ai-portfolio`. Today: MLflow 3.16 on Postgres +
MinIO (S3 API) via Docker Compose, a project registry, an init script that owns experiment
ids, a verifier that proves each sibling can log, and agent context (portfolio-level
CLAUDE.md/AGENTS.md + a Claude Code plugin). Next: AWS demo (M2), central database (M3),
LiteLLM gateway + metrics + MCP (M4), deploy modules + template (M5).

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
| D12 | Validation never touches the live stack. Compose project names are machine-global, so a `make down` in CI or a no-mistakes worktree used to stop the live `nmp-central`. The Makefile switches to project/network `nmp-central-validate` on ports 15000/15432/19000/19001 whenever `CI`, `NO_MISTAKES_GATE` or `VALIDATION` is set or the checkout lives under `.no-mistakes/`; `make mode` shows which. Validation `down` also drops its volumes. |

## Layout

See README. The registry (`registry/projects.yaml`) is the source of truth for projects,
experiments, env-id variables and smoke commands; `scripts/_registry.py` is the loader.

## Runbooks

- Start / stop / reset: `make up`, `make down`, `make nuke` (asks), `make logs`.
- Bump the server: edit `services/mlflow/Dockerfile`, `make up`, `make mlflow-db-upgrade`.
- New project: `docs/onboarding.md`.
- Verify the platform end to end: `make check` (all) or `make check ARGS="--only P2"`.
- OTLP ingest check without any sibling: `make otlp-smoke EXPERIMENT_ID=<id>`.

## Rules

- Never commit `.env`, `.mlflow-ids.env`, volumes, Terraform state or any real credential.
- Ports 5000 / 5432 / 9000 / 9001 are the platform's. Siblings must not squat them.
- Everything MLflow-related in the siblings is best-effort-silent (they swallow tracking
  errors). `make check` is the only way to know the platform works; run it after any change.
- `.lavish/` is tracked. Never add it to `.gitignore`.
- Public repo: account ids, SSO URLs and hostnames stay out of code and docs.
