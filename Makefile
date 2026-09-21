# nmp-central-ai — shared services for the nmp-ai-portfolio siblings.
SHELL := /bin/bash
.DEFAULT_GOAL := help
COMPOSE ?= docker compose
MLFLOW_URI ?= http://localhost:$(or $(MLFLOW_PORT),5000)
PORTFOLIO_DIR := $(abspath ..)

help: ## list targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-24s\033[0m %s\n", $$1, $$2}'

# ---- local stack ---------------------------------------------------------
up: ## start postgres, minio, mlflow (builds the mlflow image once)
	$(COMPOSE) up -d --build --wait
	@echo "MLflow UI: $(MLFLOW_URI)   MinIO console: http://localhost:$(or $(MINIO_CONSOLE_PORT),9001)"

down: ## stop the stack (volumes kept)
	$(COMPOSE) down

nuke: ## stop the stack AND delete volumes (asks first)
	@read -p "Delete pgdata + miniodata volumes? [y/N] " a && [ "$$a" = "y" ] && $(COMPOSE) down -v || echo "kept"

logs: ## follow logs
	$(COMPOSE) logs -f --tail=100

ps: ## container status
	$(COMPOSE) ps

status: ## is the platform healthy?
	@curl -fsS $(MLFLOW_URI)/health >/dev/null && echo "mlflow  OK  $(MLFLOW_URI)" || (echo "mlflow  DOWN  run: make -C $(CURDIR) up"; exit 1)
	@$(COMPOSE) ps --format '{{.Name}}\t{{.Status}}' | sed 's/^/  /'

mlflow-init: ## create every experiment in registry/projects.yaml (idempotent), write .mlflow-ids.env
	uv run scripts/mlflow_init.py --uri $(MLFLOW_URI)

mlflow-db-upgrade: ## run MLflow schema migration after bumping the server image
	$(COMPOSE) run --rm --no-deps mlflow mlflow db upgrade postgresql://$${MLFLOW_DB_USER:-mlflow}:$${MLFLOW_DB_PASSWORD:-mlflow}@postgres:5432/mlflow

check: ## M1 verifier: smoke every registered project and confirm a run/trace landed
	uv run scripts/check_projects.py --uri $(MLFLOW_URI) $(ARGS)

otlp-smoke: ## send one OTLP span to the central server (EXPERIMENT_ID=<id>)
	uv run scripts/otlp_smoke.py --uri $(MLFLOW_URI) --experiment-id $(EXPERIMENT_ID)

# ---- agent context -------------------------------------------------------
install-agent-context: ## install portfolio-level CLAUDE.md + AGENTS.md so every sibling sees PLATFORM.md
	@for f in CLAUDE AGENTS; do \
	  src=agent/portfolio.$$f.md; dst=$(PORTFOLIO_DIR)/$$f.md; \
	  if [ -e $$dst ] && ! cmp -s $$src $$dst && [ "$(FORCE)" != "1" ]; then \
	    echo "$$dst exists and differs; re-run with FORCE=1 to overwrite"; exit 1; fi; \
	  cp $$src $$dst && echo "installed $$dst"; done

plugin-validate: ## validate the Claude Code plugin + marketplace manifests
	claude plugin validate . && claude plugin validate plugins/nmp-platform

# ---- dev hygiene ----------------------------------------------------------
setup: ## install python deps for the scripts
	uv sync --all-groups

fmt: ## format
	uv run ruff format .

lint: ## lint + typecheck
	uv run ruff check . && uv run mypy scripts

test: ## unit tests for the scripts
	uv run pytest -q

# ---- aws (M2) --------------------------------------------------------------
aws-plan: ## terraform plan for the demo stack
	cd infra/terraform/central && terraform init -input=false && terraform plan

aws-sleep: ## stop the demo EC2 + RDS between demos
	@echo "M2: implemented with infra/terraform/central outputs"; exit 1

aws-wake: ## start them again
	@echo "M2: implemented with infra/terraform/central outputs"; exit 1

.PHONY: help up down nuke logs ps status mlflow-init mlflow-db-upgrade check otlp-smoke install-agent-context plugin-validate setup fmt lint test aws-plan aws-sleep aws-wake
