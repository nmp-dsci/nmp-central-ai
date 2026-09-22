# CLAUDE.md — nmp-central-ai

> Read [`AGENTS.md`](./AGENTS.md) first (what this is, decisions D1–D19, runbooks). The
> outward contract is [`PLATFORM.md`](./PLATFORM.md); the plan of record is
> `ai_specs/s00_project_plan.md`. This file is a pointer plus the rules that bite.

## Quick reference

- `make up` · `make status` · `make mlflow-init` · `make db-init` · `make check` · `make install-agent-context`
- `make setup && make lint && make test` for the scripts (uv, ruff, mypy strict, pytest)
- `make plugin-validate` after touching `plugins/` or `.claude-plugin/`

## Rules

- **The registry is the source of truth.** Experiments, env-id variables, smoke commands and
  every project database (name, roles, extensions, URL vars) live in `registry/projects.yaml`.
  Never hardcode an experiment id or a database URL anywhere; `make db-init` writes `.db-urls.env`.
- **One Postgres, one database per project (D13).** Roles are cluster-global and registry-owned
  (D15). Never `DROP DATABASE`, never `down -v` a stack that owned data; back up with
  `make db-backup DB=<db>` before any migration step (D14/D16).
- **`make mode` before `make down`.** A validation checkout (CI, no-mistakes worktree, `VALIDATION=1`) drives
  project `nmp-central-validate` on :15000, never the live `nmp-central` (D12). Do not set
  `COMPOSE_PROJECT_NAME` / `PLATFORM_NETWORK` by hand.
- **Do not change ports or the network name** (`nmp-central`, 5000/5432/9000/9001) without
  updating PLATFORM.md and every sibling; that is what this repo exists to prevent.
- **Bump the MLflow server deliberately:** pin in `services/mlflow/Dockerfile`, then
  `make mlflow-db-upgrade`, then `make check`.
- **Siblings fail silently on tracking errors.** After any platform change, `make check` is
  the only proof. Treat a red row as a platform bug until shown otherwise.
- **Public repo.** No secrets, account ids, SSO URLs or real hostnames in code or docs.
  `.env.example` carries names and local-only defaults.
- Never add `.lavish/` to `.gitignore`.
