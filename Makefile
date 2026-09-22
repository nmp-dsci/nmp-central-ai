# nmp-central-ai — shared services for the nmp-ai-portfolio siblings.
SHELL := /bin/bash
.DEFAULT_GOAL := help
COMPOSE ?= docker compose
PORTFOLIO_DIR := $(abspath ..)

# ---- live vs validation ----------------------------------------------------
# The live stack is compose project `nmp-central` (network `nmp-central`, ports
# 5000/5432/9000/9001) and is what the siblings talk to. Anything that merely
# validates this repo — GitHub CI, a no-mistakes worktree, or VALIDATION=1 —
# gets its own project name, network, volumes and ports, so `make down` there
# tears down only its own containers. Docker compose project names are
# machine-global; without this, a validation run's `down` stopped the live stack.
ifneq (,$(CI)$(NO_MISTAKES_GATE)$(VALIDATION)$(findstring /.no-mistakes/,$(CURDIR)))
MODE := validation
export COMPOSE_PROJECT_NAME ?= nmp-central-validate
export PLATFORM_NETWORK ?= nmp-central-validate
export MLFLOW_PORT ?= 15000
export POSTGRES_PORT ?= 15432
export MINIO_PORT ?= 19000
export MINIO_CONSOLE_PORT ?= 19001
else
MODE := live
export COMPOSE_PROJECT_NAME ?= nmp-central
export PLATFORM_NETWORK ?= nmp-central
export MLFLOW_PORT ?= 5000
endif
MLFLOW_URI ?= http://localhost:$(MLFLOW_PORT)

help: ## list targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-24s\033[0m %s\n", $$1, $$2}'

# ---- local stack ---------------------------------------------------------
up: ## start postgres, minio, mlflow (builds the mlflow image once)
	$(COMPOSE) up -d --build --wait
	@echo "MLflow UI: $(MLFLOW_URI)   MinIO console: http://localhost:$(or $(MINIO_CONSOLE_PORT),9001)"

down: ## stop the stack (live: volumes kept; validation: volumes removed too)
	$(COMPOSE) down $(if $(filter validation,$(MODE)),-v)

nuke: ## stop the stack AND delete volumes (asks first)
	@read -p "Delete pgdata + miniodata volumes? [y/N] " a && [ "$$a" = "y" ] && $(COMPOSE) down -v || echo "kept"

logs: ## follow logs
	$(COMPOSE) logs -f --tail=100

logs-tail: ## last 50 mlflow log lines (CI)
	$(COMPOSE) logs --tail=50 mlflow

ps: ## container status
	$(COMPOSE) ps

mode: ## which stack this checkout drives (live | validation) and its names/ports
	@echo "mode=$(MODE) project=$(COMPOSE_PROJECT_NAME) network=$(PLATFORM_NETWORK) mlflow=$(MLFLOW_URI)"

status: ## is the platform healthy?
	@curl -fsS $(MLFLOW_URI)/health >/dev/null && echo "mlflow  OK  $(MLFLOW_URI)" || (echo "mlflow  DOWN  run: make -C $(CURDIR) up"; exit 1)
	@$(COMPOSE) ps --format '{{.Name}}\t{{.Status}}' | sed 's/^/  /'

mlflow-init: ## create every experiment in registry/projects.yaml (idempotent), write .mlflow-ids.env
	uv run scripts/mlflow_init.py --uri $(MLFLOW_URI)

mlflow-db-upgrade: ## run MLflow schema migration after bumping the server image
	$(COMPOSE) run --rm --no-deps mlflow mlflow db upgrade postgresql://$${MLFLOW_DB_USER:-mlflow}:$${MLFLOW_DB_PASSWORD:-mlflow}@postgres:5432/mlflow

check: ## verifier: every registered project logs to the central MLflow AND its database lives here
	uv run scripts/check_projects.py --uri $(MLFLOW_URI) $(ARGS)
	uv run scripts/check_databases.py --base-uri $(POSTGRES_URI) --mlflow-uri $(MLFLOW_URI) $(ARGS)

# ---- central postgres (M3) --------------------------------------------------
POSTGRES_URI ?= postgresql://localhost:$(or $(POSTGRES_PORT),5432)
STAMP := $(shell date -u +%Y%m%dT%H%M%SZ)

db-init: ## create every role, database and extension in registry/projects.yaml (idempotent), write .db-urls.env
	POSTGRES_PORT=$(or $(POSTGRES_PORT),5432) uv run scripts/db_init.py --psql "$(COMPOSE) exec -T postgres psql" $(ARGS)

db-urls: ## print the database URLs each project should paste into its .env
	@test -f .db-urls.env || { echo "run: make db-init"; exit 1; }
	@cat .db-urls.env

db-check: ## M3 verifier only (make check runs it too)
	uv run scripts/check_databases.py --base-uri $(POSTGRES_URI) --mlflow-uri $(MLFLOW_URI) $(ARGS)

db-psql: ## psql as the superuser into DB (default: the maintenance db)
	$(COMPOSE) exec postgres psql -U nmp -d $(or $(DB),nmp)

db-backup: ## pg_dump -Fc DB=<database> to backups/<db>-<utc>.dump (SRC=<other container> SRC_USER=… SRC_DB=… to dump an old server)
	@test -n "$(DB)" || { echo "usage: make db-backup DB=<database> [SRC=<container> SRC_USER=<user> SRC_DB=<db>]"; exit 1; }
	@mkdir -p backups
ifeq ($(SRC),)
	$(COMPOSE) exec -T postgres pg_dump -Fc -U nmp -d $(DB) -f /backups/$(DB)-$(STAMP).dump
else
	docker exec $(SRC) pg_dump -Fc -U $(or $(SRC_USER),postgres) -d $(or $(SRC_DB),$(DB)) $(if $(SCHEMA),-n $(SCHEMA)) > backups/$(DB)-$(STAMP).dump
endif
	@ls -la backups/$(DB)-$(STAMP).dump

db-restore: ## pg_restore -j4 --no-owner FILE=backups/<file>.dump into DB=<database> [ROLE=<owner of restored objects>] [NO_PRIVS=1] [SKIP=<regex of TOC entries to drop, e.g. "DEFAULT ACL">]
	@test -n "$(DB)" -a -n "$(FILE)" || { echo "usage: make db-restore DB=<database> FILE=backups/<file>.dump [ROLE=<role>] [NO_PRIVS=1] [SKIP=<regex>]"; exit 1; }
	$(COMPOSE) exec -T postgres sh -c 'pg_restore -l /backups/$(notdir $(FILE)) $(if $(SKIP),| grep -Ev "$(SKIP)") > /tmp/restore.toc && pg_restore -j4 --no-owner --exit-on-error -U nmp -d $(DB) $(if $(ROLE),--role=$(ROLE)) $(if $(NO_PRIVS),--no-privileges) -L /tmp/restore.toc /backups/$(notdir $(FILE))'

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

.PHONY: help up down nuke logs logs-tail ps mode status mlflow-init mlflow-db-upgrade check db-init db-urls db-check db-psql db-backup db-restore otlp-smoke install-agent-context plugin-validate setup fmt lint test aws-plan aws-sleep aws-wake
