# User-global instructions for DeepSeek Harness

Installed as `~/.dsh/AGENTS.md` by `make dsh-install` in nmp-central-ai (D39). dsh loads it
before the project's own `AGENTS.md`, and the project's file wins where they differ.

- Inside `~/git/nmp-ai-portfolio/`, read `~/git/nmp-ai-portfolio/nmp-central-ai/PLATFORM.md`
  before touching MLflow, Postgres, the house UI or AWS. It is the shared-platform contract.
  dsh does not load the portfolio-level `AGENTS.md` that normally points there, because it
  sits above each repo's git root.
- Never read, print or copy `.env` files, `*.pem` files, `~/.dsh/.credentials.yaml` or any
  other credential file. Ask the user for the value you need instead.
- Never push, merge or deploy: no `git push`, `gh pr merge`, `terraform apply` or deploy
  workflows. The user does that.
