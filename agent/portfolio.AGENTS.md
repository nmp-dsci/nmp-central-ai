# AGENTS.md — nmp-ai-portfolio (portfolio level)

Installed by `make -C nmp-central-ai install-agent-context`; source lives at
`nmp-central-ai/agent/portfolio.AGENTS.md`. Tools that read AGENTS.md (Codex and others)
get the same platform contract Claude Code gets via CLAUDE.md.

Every project in this folder uses the shared platform in `nmp-central-ai` for MLflow
(tracking, traces, prompt and model registry) and, later, the database, LLM gateway and
deploy modules. Read `nmp-central-ai/PLATFORM.md` before touching tracking, evaluation or
deployment code in any project. Never start a project-local MLflow, Postgres or gateway.

Per-project `AGENTS.md` files take precedence for everything else.
