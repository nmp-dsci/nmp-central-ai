# CLAUDE.md — nmp-ai-portfolio (portfolio level)

This file is installed by `make -C nmp-central-ai install-agent-context` and is loaded by
Claude Code in **every** project under this folder, because Claude Code reads CLAUDE.md from
the working directory and each directory above it. Do not edit it here; edit
`nmp-central-ai/agent/portfolio.CLAUDE.md` and re-run the target.

## Shared services

Every project here uses the shared platform in `nmp-central-ai` for MLflow (tracking,
traces, prompt and model registry) and, later, the database, LLM gateway and deploy modules.
The contract, URLs, env vars and rules are in the imported file below. Never spin up a
project-local copy of a platform service.

@~/git/nmp-ai-portfolio/nmp-central-ai/PLATFORM.md

## Conventions across the portfolio

- Each project is its own git repo with its own `CLAUDE.md` + `AGENTS.md`; those win over this file.
- Python: `uv` for everything, Ruff, mypy strict. TypeScript: React + Vite.
- Keys come from `~/.env` or the project's `.env`; never hardcode, never commit.
- Never add `.lavish/` to a `.gitignore`.
