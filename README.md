# nmp-central-ai

Shared services for the [nmp-dsci](https://github.com/nmp-dsci) AI portfolio: one MLflow
server (tracking, traces, prompt registry, model registry) backed by Postgres and
S3-compatible storage, running locally with Docker Compose and, in the same shape, as a
small demo on AWS. Later milestones add a central database, an LLM gateway with per-project
budgets, shared deploy modules and a project template.

It exists because every sibling project had grown its own MLflow on its own port
(5000 / 5500 / 5600 / 5601), its own database and its own copy of the deploy Terraform.
This repo is the platform-team answer: publish once, consume everywhere, version centrally.
Coding agents working in the sibling repos are first-class consumers: see
[PLATFORM.md](PLATFORM.md) and the `nmp-platform` Claude Code plugin in `plugins/`.

## Quickstart

```bash
make up            # postgres + minio + mlflow  ->  http://localhost:5000
make mlflow-init   # create every experiment in registry/projects.yaml, write .mlflow-ids.env
make status        # health
make check         # prove each registered sibling can log to the server (no paid LLM calls)
make install-agent-context   # portfolio-level CLAUDE.md / AGENTS.md so agents see PLATFORM.md
```

Sibling projects need exactly one thing: `MLFLOW_TRACKING_URI=http://localhost:5000`
(or `http://mlflow:5000` from inside a compose stack that joins the external network
`nmp-central`). OTLP exporters post to `/v1/traces` with `x-mlflow-experiment-id`.

## Layout

| path | what |
|---|---|
| `docker-compose.yml` | postgres (pgvector/pg16), minio, mlflow 3.16 — the local platform |
| `services/mlflow/` | the pinned server image |
| `registry/projects.yaml` | the project map: who uses which experiments, how to smoke-test them |
| `scripts/` | `mlflow_init.py` (experiments + ids), `check_projects.py` (M1 verifier), `otlp_smoke.py` |
| `PLATFORM.md` | the contract every agent and person reads |
| `agent/` | portfolio-level `CLAUDE.md` / `AGENTS.md` installed one directory up |
| `plugins/nmp-platform/` | Claude Code plugin: `platform-mlflow`, `platform-onboard` skills |
| `docs/` | onboarding and runbooks |
| `infra/terraform/` | AWS demo stack (M2) |
| `ai_specs/` | plan of record (`s00_project_plan.md`) |
| `.lavish/` | review artifacts |

## Milestones

M0 repo + local stack · M1 migrate ConvFinQA-agent, DABStep-loop, tau2-loop, data-qa-agent
(then transcript-rag-agent) · M2 AWS demo on one Graviton EC2 + RDS + S3 · M3 central
database · M4 gateway, secrets, metrics, MCP server · M5 deploy modules and template.
Details and decisions: [ai_specs/s00_project_plan.md](ai_specs/s00_project_plan.md).

## Development

```bash
make setup && make lint && make test     # uv, ruff, mypy, pytest for the scripts
make plugin-validate                      # claude plugin validate
```

MIT licensed.
