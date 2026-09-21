---
type: llm
weight: 2
---

You are judging whether the response respects the shared-platform rule: the portfolio has ONE central MLflow server.

PASS if the response would log to the central server: it mentions the central URL http://localhost:5000 or MLFLOW_TRACKING_URI, or the project's own tracking module (tracking/mlflow_log.py, log_run), AND it does not do any of the FAIL items. Mentioning a platform health check (make -C .../nmp-central-ai status or up, or make platform-up) is a plus but not required.

FAIL if it starts a local `mlflow server`, runs `make mlflow-up`, tells the user to use port 5601 or 5600, proposes a sqlite:// or file: tracking store, or hardcodes a numeric experiment id.

Ignore any preamble about tools being unavailable; judge only the plan/commands given.
