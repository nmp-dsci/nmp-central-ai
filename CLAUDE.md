# CLAUDE.md — nmp-central-ai

> Read [`AGENTS.md`](./AGENTS.md) first (what this is, decisions D1–D10, runbooks). The
> outward contract is [`PLATFORM.md`](./PLATFORM.md); the plan of record is
> `ai_specs/s00_project_plan.md`. This file is a pointer plus the rules that bite.

## Quick reference

- `make up` · `make status` · `make mlflow-init` · `make check` · `make install-agent-context`
- `make setup && make lint && make test` for the scripts (uv, ruff, mypy strict, pytest)
- `make plugin-validate` after touching `plugins/` or `.claude-plugin/`

## Rules

- **The registry is the source of truth.** Experiments, env-id variables and smoke commands
  live in `registry/projects.yaml`. Never hardcode an experiment id anywhere.
- **Do not change ports or the network name** (`nmp-central`, 5000/5432/9000/9001) without
  updating PLATFORM.md and every sibling; that is what this repo exists to prevent.
- **Bump the MLflow server deliberately:** pin in `services/mlflow/Dockerfile`, then
  `make mlflow-db-upgrade`, then `make check`.
- **Siblings fail silently on tracking errors.** After any platform change, `make check` is
  the only proof. Treat a red row as a platform bug until shown otherwise.
- **Public repo.** No secrets, account ids, SSO URLs or real hostnames in code or docs.
  `.env.example` carries names and local-only defaults.
- Never add `.lavish/` to `.gitignore`.
