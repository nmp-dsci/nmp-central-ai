---
type: llm
weight: 2
---

You are judging an onboarding plan for a project joining a shared MLflow platform (nmp-central-ai).

PASS if the plan includes at least THREE of these five and none of the FAIL items:
1. add an entry to nmp-central-ai/registry/projects.yaml
2. run mlflow-init (make -C ... mlflow-init) to get experiment ids
3. set the project's default tracking URI to the central server http://localhost:5000, keeping MLFLOW_TRACKING_URI as override
4. a zero-cost smoke command that logs one run without calling a paid model
5. verify with `make check` (optionally `ARGS="--only <ID>"`)

FAIL if the plan proposes a project-local MLflow server, a sqlite:// or file: store, a new port, or hardcodes a numeric experiment id.

Ignore any preamble about tools being unavailable; judge only the plan.
