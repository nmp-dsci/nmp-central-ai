---
name: platform-onboard
description: Onboard a project in nmp-ai-portfolio to the nmp-central-ai shared platform, or migrate one off its own MLflow server. Use when asked to "put this project on the platform", "use the central MLflow", "migrate off port 5600/5601/5500", "add this to the registry", or when a new project needs tracking.
---

# platform-onboard

Follow `~/git/nmp-ai-portfolio/nmp-central-ai/docs/onboarding.md`. Summary:

1. Add a registry entry in `nmp-central-ai/registry/projects.yaml` (id, name, path, client python|otlp, experiments, verify, a zero-cost `smoke` command).
2. `make -C ~/git/nmp-ai-portfolio/nmp-central-ai mlflow-init` → ids in `.mlflow-ids.env`.
3. In the project: default tracking URI → `http://localhost:5000` (or `OTLP_ENDPOINT=http://mlflow:5000` in compose); delete its own mlflow service / `mlflow-up` target / sqlite or file store; keep `MLFLOW_TRACKING_URI` as override; client floor `mlflow>=3.12,<4`.
4. Compose projects: add `networks: { default: {}, nmp-central: { external: true } }` and `networks: [default, nmp-central]` on each service that exports to MLflow. Always include `default`.
5. Add a `platform-up` Make target and a `/health` preflight that names it on failure. No silent fallbacks.
6. `make -C ~/git/nmp-ai-portfolio/nmp-central-ai check ARGS="--only <ID>"` must PASS; set `status: migrated`.
7. Update the project's README / AGENTS.md / CLAUDE.md; old stores are archived, never deleted.

Work on a branch in the sibling repo; do not push. Report the diff and the PASS row.
