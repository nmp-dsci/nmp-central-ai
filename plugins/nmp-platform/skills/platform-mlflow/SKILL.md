---
name: platform-mlflow
description: Use the central nmp-central-ai MLflow server from any nmp-ai-portfolio project. Use when asked to log a run, log or inspect traces, compare runs, register or promote a model, use the prompt registry, find an experiment id, check whether MLflow is up, or when code touches MLFLOW_TRACKING_URI, mlflow.set_experiment, OTLP_ENDPOINT or x-mlflow-experiment-id.
---

# platform-mlflow

The portfolio has ONE MLflow server. Contract: `~/git/nmp-ai-portfolio/nmp-central-ai/PLATFORM.md`.

## Facts

- URL from the host: `http://localhost:5000`. From a compose stack on network `nmp-central`: `http://mlflow:5000`.
- The only coupling is `MLFLOW_TRACKING_URI`. Projects default to the central URL; the env var overrides.
- OTLP: `POST <url>/v1/traces` with header `x-mlflow-experiment-id: <numeric id>`.
- Backend is Postgres + S3-API artifacts; the server proxies artifacts. Clients never need S3 creds.
- Server 3.16.x. Clients: `mlflow>=3.12,<4` (the OTLP ingest needs >= 3.6).
- Experiment ids are assigned by the server. Get them from `make -C ~/git/nmp-ai-portfolio/nmp-central-ai mlflow-init`, which writes `.mlflow-ids.env`. Never hardcode an id.
- Registry of every project, experiment and model name: `nmp-central-ai/registry/projects.yaml`.

## Do this

1. Before any tracking work: `make -C ~/git/nmp-ai-portfolio/nmp-central-ai status`. If DOWN, run `... up`. Do not fall back to sqlite/file stores, do not start `mlflow server`, do not change ports.
2. Log with the project's own tracking module if it has one (ConvFinQA `tracking/mlflow_log.py`, DABStep/tau2 `tracking/mlflow_log.py`); they already set the URI, experiment, tags and artifacts. Otherwise:
   ```python
   import mlflow, subprocess

   mlflow.set_experiment("<project>/<purpose>")  # new experiments use this naming
   with mlflow.start_run(run_name="...") as run:
       mlflow.set_tags(
           {
               "project": "<project>",
               "git_sha": subprocess.check_output(["git", "rev-parse", "--short", "HEAD"])
               .decode()
               .strip(),
               "env": "local",
           }
       )
       mlflow.log_params({...})
       mlflow.log_metrics({...})
       mlflow.log_artifact("path")
   ```
3. Tracing: prefer the framework autolog the project already uses (`mlflow.pydantic_ai.autolog()`, `mlflow.langchain.autolog()`), else `with mlflow.start_span(name, span_type="CHAIN") as s: s.set_inputs(...); s.set_outputs(...)`. Keep span trimming on; never set `MLFLOW_TRACE_FULL=1` on shared runs.
4. Query:
   ```python
   from mlflow import MlflowClient

   c = MlflowClient()  # honours MLFLOW_TRACKING_URI
   exp = c.get_experiment_by_name("dabstep-loop")
   runs = c.search_runs(
       [exp.experiment_id],
       filter_string="tags.env = 'local'",
       order_by=["attributes.start_time DESC"],
       max_results=20,
   )
   traces = c.search_traces(locations=[exp.experiment_id], max_results=20)
   ```
5. Registry / prompts: registered models and prompts are global on the shared server. Only touch names that belong to the project you are in (see the registry file). Aliases in use: `champion`, `challenger`.
6. Verify after changing anything tracking-related: `make -C ~/git/nmp-ai-portfolio/nmp-central-ai check ARGS="--only <ID>"`.

## Never

- Start a local MLflow server, create a `mlruns/`, `.mlflow/` or `mlflow.db` in a project.
- Hardcode `127.0.0.1:5600`, `:5601`, `:5500` or any experiment id.
- Log secrets, API keys, raw customer data or PII into params, tags, artifacts or spans.
- Delete or rename another project's experiments, models or prompts.
