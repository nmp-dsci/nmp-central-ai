# Onboarding a project to the platform

Ten minutes, no code in the platform repo beyond one registry entry.

1. **Register it.** Add an entry to `registry/projects.yaml`: `id`, `name`, `path`,
   `mlflow.client` (`python` or `otlp`), the experiment names it will use (new ones as
   `<project>/<purpose>`), `verify` (`runs` / `traces` / `both`) and a `smoke` command that
   logs one run or trace **without calling a paid model** (re-log a committed run folder,
   call the project's own tracking helper, or export one span).
2. **Create the experiments.** `make mlflow-init` (idempotent). It prints ids and writes
   `.mlflow-ids.env`; OTLP clients source that file for `x-mlflow-experiment-id`.
3. **Point the project at the platform.** Set the project's *default* tracking URI to
   `http://localhost:5000` (Python) or `OTLP_ENDPOINT=http://mlflow:5000` (compose), and delete
   any project-local MLflow service, `make mlflow-up` target, sqlite or `file:` store.
   Keep `MLFLOW_TRACKING_URI` as the override. Bump the client floor to `mlflow>=3.12,<4`.
4. **If the project runs in compose,** add to its `docker-compose.yml`:
   ```yaml
   networks:
     default: {}
     nmp-central: { external: true }
   ```
   and `networks: [default, nmp-central]` on every service that talks to MLflow. Listing
   `default` too is essential: naming only `nmp-central` detaches the service from its own stack.
5. **Fail fast, not silent.** Give the project a `platform-up` Make target that runs
   `make -C ../nmp-central-ai up`, and a preflight that curls `<uri>/health` before any
   eval, printing that target's name on failure.
6. **Verify.** `make check ARGS="--only <ID>"` in this repo must show PASS. Then set the
   registry entry's `status: migrated`.
7. **Docs.** Update the project's README / AGENTS.md / CLAUDE.md so the old port and store
   are gone, and note the archive location of any old store you left on disk.

Old stores are never deleted by the platform; they are archived read-only (decision D2).
