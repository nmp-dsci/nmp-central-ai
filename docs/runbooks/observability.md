# Runbook — observability (Langfuse + MLflow, D33–D36)

Langfuse is **built but not started**. This runbook covers turning it on, moving a project's
traces onto it, and the things that will bite.

## The split, in one line

Traces, cost, sessions and online eval go to **Langfuse**. Runs, params, artifacts, prompts and
the model registry stay in **MLflow**. Nothing moves out of MLflow except traces.

## Before you start: the host

```bash
make langfuse-doctor
```

Langfuse's documented floor is 4 cores / 16 GiB / 100 GiB. On a Mac the binding number is the
**Docker VM's** memory, not the host's, because every container shares it. As measured on
2026-10-02 this machine reported:

```
  ok    docker cores          10        want >= 4
  FAIL  docker VM memory     7.7 GiB    want >= 16 GiB
  FAIL    of which free      4.6 GiB    want >= 5 GiB (3.1 GiB already in use)
  FAIL  host disk free      95.8 GiB    want >= 100 GiB
```

The host has 32 GiB, so the VM is a **setting, not a limit**: Docker Desktop → Settings →
Resources → Memory. Raise it to ~20 GiB and re-run. Disk is the other one — `docker system df`
showed ~67 GB reclaimable (`docker system prune` and the build cache) if you need the room.

`make langfuse-up` refuses to start while the doctor fails. That is deliberate: a half-started
ClickHouse on a full VM takes the rest of the stack down with it. Override only if you know why:

```bash
make langfuse-up GATE=0
```

## Starting it

```bash
make db-init        # creates the `langfuse` database and role from the registry (D35)
make langfuse-up    # doctor, then langfuse-init, then the profile
make status         # the langfuse row turns from "off" to "OK"
```

`make langfuse-up` calls `make langfuse-init` for you, which writes `.langfuse.env` with a fresh
`SALT`, `ENCRYPTION_KEY` and `NEXTAUTH_SECRET` at mode 0600. It is gitignored — this is a public
repo and those three protect every API key Langfuse issues. It never overwrites: to rotate,
delete the file first, and expect to re-issue project keys.

Stop it without touching the rest of the stack:

```bash
make langfuse-down
```

## Moving a project's traces

Never flip a project straight over. The registry has a middle state for this.

1. Declare the move in `registry/projects.yaml`:

   ```yaml
   observability:
     backend: both              # export to MLflow AND Langfuse
     langfuse_project: data-qa  # instance-global, so unique across the registry
   ```

2. Point the exporter at Langfuse. For an OTLP project this is an endpoint and a header —
   nothing else changes:

   ```
   # MLflow                    -> <mlflow>/v1/traces   + x-mlflow-experiment-id: <id>
   # Langfuse                  -> <langfuse>/api/public/otel/v1/traces
   #                              + Authorization: Basic base64(pk-lf-…:sk-lf-…)
   ```

3. Run both for long enough to compare, then narrow `backend` to `langfuse` and remove the
   MLflow trace export. Runs, params and artifacts keep going to MLflow — do not touch them.

## Gotchas

- **OTLP over HTTP only.** Langfuse does not support gRPC. An exporter configured for
  `grpc` must move to `http/protobuf`.
- **ClickHouse wants port 9000, and MinIO already has it** on this host. That is why neither
  ClickHouse nor Redis publishes a port in our compose file — they are reachable only from
  inside the network. Do not "helpfully" add a `ports:` entry.
- **A declared-but-empty `observability:` block is an error**, not an absent one. This is
  deliberate: a duplicated `ui:` key once loaded cleanly because YAML is last-key-wins, and
  the bug survived review. Declared means validated.
- **`langfuse_project` must be absent when `backend: mlflow`.** A stale project name left
  behind after a rollback is how the registry stops being the truth.
- **No backup yet.** `make db-backup` covers Postgres; ClickHouse will hold the traces and has
  no equivalent target. Treat trace data as expendable until that exists (scope item S6).
- **The console is host-only** (`127.0.0.1:3100`), like the DB UI, because it can read every
  project's traces. Do not publish it on `0.0.0.0`.

## What is deliberately not built yet

- `make check` does not yet prove a project's traces reach Langfuse (S5).
- No ClickHouse backup (S6).
- No prompt migration — the 65 prompt versions stay in MLflow, by decision (S8, parked).
