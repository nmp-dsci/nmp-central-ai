# s00 — nmp-central-ai project plan (plan of record)

Status: decided 2026-09-21 · Review artifact: `.lavish/s00_central-ai-plan.html`

## What this is

`nmp-central-ai` is the shared-services platform for every project under
`~/git/nmp-ai-portfolio/`. It replaces per-project copies of MLflow, databases,
gateways and deploy infrastructure with one catalogue of services that runs
locally via Docker Compose and, in the same shape, on AWS (ap-southeast-2).
In current vocabulary: an internal developer platform for AI systems, with
coding agents as a first-class consumer.

Survey evidence (2026-09-21): 6 sibling projects configure MLflow in 5
incompatible ways on 4 hand-picked ports (5000 / 5500 / 5600 / 5601); 6 carry
near-identical App Runner Terraform; 14 carry the AGENTS.md + CLAUDE.md pair.

## Guardrails

- The only coupling a sibling has to the platform in M1 is `MLFLOW_TRACKING_URI`.
- Local mirrors AWS in shape: Postgres backend + S3-compatible artifacts from day one
  (MinIO locally, RDS + S3 in AWS).
- Databricks projects stay on Databricks-managed MLflow; not in scope.
- A service enters the catalogue only with duplication count >= 2 and its own plan.
  Frontends are never centralised.
- Dev is local with real runs. AWS is a lightweight demo with no live data.

## Decisions

| ID | Decision | Outcome |
|----|----------|---------|
| D1 | Local MLflow port | 5000 (MLflow default) |
| D2 | Old runs | Fresh start; old sqlite/file stores archived read-only, never deleted |
| D3 | Shared Python helper | Env var only in M1; helper package later |
| D4 | AWS compute (demo) | One Graviton EC2 t4g.small running the same compose file, Caddy HTTPS + basic-auth, RDS + S3; ECS Express Mode is the upgrade path |
| D5 | RDS engine | RDS Postgres db.t4g.micro, 20 GB gp3, single-AZ, stoppable |
| D6 | Repo name / licence | nmp-central-ai, MIT, public under nmp-dsci |
| D7 | Agent onboarding | L1 portfolio-level CLAUDE.md + AGENTS.md importing PLATFORM.md (M0); L2 Claude Code plugin with skills (M1); L3 MCP server (M4) |
| —  | Backend store | Postgres + MinIO locally; RDS + S3 in AWS |
| —  | Scope | M1 = ConvFinQA-agent, DABStep-loop, tau2-loop, data-qa-agent. transcript-rag-agent right after (M1b). Excluded: v2v-prod-agent (keeps Langfuse), databricks-propertyiq, databricks-sa-coding, CUAD-agent |
| —  | App Runner | Retired as an option: closed to new customers 2026-04-30. Six sibling stacks migrate in M5 |

## Target shape

```
sibling project ──MLFLOW_TRACKING_URI=http://localhost:5000──┐
sibling compose ──http://mlflow:5000 on network nmp-central──┤
data-qa OTLP    ──/v1/traces + x-mlflow-experiment-id────────┤
                                                              ▼
              nmp-central-ai/docker-compose.yml
   postgres (pgvector/pg16, :5432) ── mlflow server 3.16 (:5000) ── minio (S3 API, :9000/:9001)
              backend-store-uri postgresql://…   artifacts-destination s3://mlflow-artifacts
```

Conventions: experiment `<project>/<purpose>`; tags `project`, `git_sha`, `env`,
`billing`; experiment ids come only from `make mlflow-init`; if the server is
unreachable a project fails fast naming `make -C ../nmp-central-ai up`.

## Repo layout (M0)

```
README.md · AGENTS.md · CLAUDE.md · PLATFORM.md · LICENSE · Makefile · .env.example · .gitignore
docker-compose.yml            postgres · minio · mlflow (+ profiles: gateway, metrics)
compose.aws.yml               override: no postgres/minio; RDS + S3; caddy
services/mlflow/Dockerfile    mlflow==3.16.x + psycopg2-binary + boto3
registry/projects.yaml        project map: path, experiments, client, smoke, status
scripts/mlflow_init.py        create experiments idempotently; print ids
scripts/check_projects.py     M1 verifier
infra/terraform/bootstrap     state bucket, ECR, GitHub OIDC role
infra/terraform/central       vpc, rds, s3, ec2 compose host, secrets
infra/terraform/modules       compose-host, rds-postgres, github-oidc (later ecs-express-service)
agent/portfolio.CLAUDE.md     installed as ../CLAUDE.md (symlink) by make install-agent-context
agent/portfolio.AGENTS.md     same, for Codex
.claude-plugin/marketplace.json · plugins/nmp-platform/  skills: platform-mlflow, platform-onboard
packages/nmp-central-py/      empty until D3 revisited
docs/onboarding.md · docs/runbooks/
ai_specs/                     this file and successors
.lavish/                      review artifacts (never gitignored)
```

Public-repo checklist: no real secret ever committed; `.env.example` names only;
Terraform state in the bootstrap bucket; GitHub OIDC, no long-lived keys;
account id and SSO URL never in code; bulk data and volumes gitignored;
gitleaks in CI; no-mistakes gate before push.

## Milestones

- **M0 Repo + local stack.** Skeleton, compose (postgres, minio, mlflow), `make up`,
  `make mlflow-init`, PLATFORM.md + portfolio-level CLAUDE.md/AGENTS.md, public repo, CI smoke.
  Done when http://localhost:5000 lists the M1 experiments.
- **M1 Migrate four projects.** ConvFinQA (default URI → central; drop compose mlflow
  service and the absolute-path bind mount), DABStep (`config.py:48`), tau2 (`config.py:60`),
  data-qa (drop its mlflow service, join `nmp-central` network, OTLP to `http://mlflow:5000`,
  experiment ids from mlflow-init). Bump every client floor to mlflow>=3.12.
  Plugin `nmp-platform` with `platform-mlflow` skill, validated with `claude plugin eval`.
  Done when `scripts/check_projects.py` is all green and ports 5500/5600/5601 are free.
- **M1b transcript-rag-agent** off `file:.yt-agent/mlruns` (config.py:271, .env.example:104,
  Dockerfile:66, readme.md:283); check must assert a langchain autolog trace exists.
- **M2 AWS demo.** Terraform: RDS t4g.micro, S3, t4g.small EC2 (AL2023, Docker, SSM, no SSH),
  Caddy HTTPS + basic-auth, no ALB, no NAT. Deploy via GitHub OIDC + SSM `compose up`.
  `make aws-sleep` / `aws-wake`. DABStep logs a demo eval from CI.
  Done when an AWS-hosted run is visible and week-one bill < USD 15.
  Cost estimate (Sydney, list prices): ≈ USD 35/month on, ≈ 6 stopped. Budget alarm USD 45.
- **M3 Central database** (separate plan): per-project schemas on the same Postgres.
- **M4 Gateway + secrets + metrics:** LiteLLM proxy with per-project keys/budgets,
  Secrets Manager, Prometheus + Grafana profile, `nmp-central` MCP server.
- **M5 Modules + template:** Terraform modules, reusable workflow, six sibling demos
  off App Runner, cookiecutter replaces ai-project-template, shared evals package.

## Verification protocol (M1)

`scripts/check_projects.py` reads `registry/projects.yaml`, runs each project's
`smoke` command with `MLFLOW_TRACKING_URI` forced to the central server, then
queries the server for a run or trace created after the smoke started and tagged
with the project. One row per project; non-zero exit on any miss.

## Risks (abridged)

Central stack down → every eval fails: fail fast with a named fix. Version skew:
pin server, bump clients to >= 3.12, `mlflow db upgrade` target. data-qa experiment
ids drift: registry is the only source. Public-repo leaks: checklist + gitleaks.
Agent context goes stale: PLATFORM.md generated from registry + compose in CI.
VM to patch: AL2023 auto-updates, SSM only, disposable box (state in RDS/S3).
Sibling demos on retired App Runner: M5 migration.

## Sources

MLflow "Deploying MLflow to AWS"; AWS App Runner notice (no new customers from
2026-04-30) and Amazon ECS Express Mode docs; Claude Code docs (memory, skills,
plugin marketplaces, MCP); 2026 LLMOps stack comparisons; platformengineering.org
2026 predictions. Full links in the review artifact appendix.
