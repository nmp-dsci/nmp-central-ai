# AGENTS.md — nmp-ai-portfolio (portfolio level)

Installed by `make -C nmp-central-ai install-agent-context`; the source is
`nmp-central-ai/agent/portfolio.AGENTS.md`. Do not edit the installed copy: edit the source and
re-run the target. Every coding agent that reads `AGENTS.md` from the working directory or a parent
gets this file; `CLAUDE.md` beside it is a one-line import for tools that only read that name.

## Shared services

Every project here uses the shared platform in `nmp-central-ai` for MLflow (tracking, traces,
prompt and model registry) and, later, the database, LLM gateway and deploy modules. **Read
`~/git/nmp-ai-portfolio/nmp-central-ai/PLATFORM.md` before touching tracking, evaluation, database
or deployment code in any project:** it holds the contract, URLs, env vars and rules. Never spin up
a project-local copy of a platform service (MLflow, Postgres, MinIO, a gateway).

## Conventions across the portfolio

- Each project is its own git repo with its own `AGENTS.md`; that file wins over this one.
- One agent setup everywhere: `AGENTS.md` is the single source of truth, skills live in
  `.agents/skills/<name>/SKILL.md`, and `CLAUDE.md` / `.claude/skills` are thin shims that only
  point at them. Never put guidance in a shim. `make -C nmp-central-ai agent-check` audits every repo.
- Python: `uv` for everything, Ruff, mypy strict. TypeScript: React + Vite.
- Keys come from `~/.env` or the project's `.env`; never hardcode, never commit.
- Never add `.lavish/` to a `.gitignore`.
