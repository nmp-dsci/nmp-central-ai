# s01 — M0 + M1 build receipt (2026-09-21)

Plan of record: `s00_project_plan.md`. Everything below was executed and verified on this machine.

## M0 — repo + local stack: done

- `docker compose`: postgres (pgvector/pg16) + minio (quay.io, multi-arch pin) + mlflow 3.16.1 on network `nmp-central`.
  Two findings folded into decisions: MinIO's Docker Hub repo is gone (D8); MLflow's OTLP route
  only exists under uvicorn, `--gunicorn-opts` 404s it (D11).
- `make mlflow-init` created six experiments (ids 1–6) and wrote `.mlflow-ids.env`; `make otlp-smoke` OK.
- `PLATFORM.md` + portfolio-level `CLAUDE.md`/`AGENTS.md` installed one directory up (`make install-agent-context`).
- Plugin `nmp-platform` (skills `platform-mlflow`, `platform-onboard`): `claude plugin validate` OK,
  installed at user scope, eval suite with-plugin 1.00 / 1.00 (onboard +1.00 over the no-plugin arm).
- Scripts: ruff, mypy strict, pytest green. Secrets scan of tracked files clean.

## M1 — migrations: item-by-item receipt

| ID | Project | Disposition | Outcome | Evidence |
|----|---------|-------------|---------|----------|
| P1 | ConvFinQA-agent | migrate | **addressed** | branch `platform/central-mlflow` @ `0821637`; default URI → central; own compose mlflow service + laptop bind mount removed; `assert_reachable()` preflight; 402 tests pass; `make check --only P1` → PASS runs=1 traces=1 |
| P2 | DABStep-loop | migrate | **addressed** | `platform/central-mlflow` @ `49f37b1`; default URI → central; `mlflow-up` → `platform-up` + `platform-status` preflight; own compose file deleted; PASS runs=1 |
| P3 | tau2-loop | migrate | **addressed** | `platform/central-mlflow` @ `9cb0340` (from `eval-submission`); same changes; PASS runs=1 |
| P4 | transcript-rag-agent | defer | **deferred** (by decision, M1b) | registry `status: deferred`; no code touched |
| P5 | data-qa-agent | migrate | **addressed** | `platform/central-mlflow` @ `e412da6`; own mlflow service removed; joined `nmp-central`; ids from `.mlflow-ids.env` (6); real `GET /me` trace landed in experiment 6; PASS traces=1 |

Final `make check`: P1 PASS · P2 PASS · P3 PASS · P5 PASS · P4 skip (deferred) · X1–X4 skip.
Ports 5500 / 5600 / 5601 are free. Old stores (`mlruns/`, `.mlflow/`) archived on disk, untouched (D2).

## Not done on purpose / follow-ups

- Sibling branches are committed, **not pushed**; open PRs (or run no-mistakes) per repo.
- DABStep / tau2: run `make snapshot` only after real runs are re-logged on the central server.
- data-qa: `agent-worker`/`handover-poller` pick up the new network on next `make up`; consider adding
  `mlflow-preflight` to `make eval`.
- M1b: transcript-rag-agent (registry P4) — set its smoke, migrate off `file:.yt-agent/mlruns`.
- M2: AWS demo on one Graviton EC2 (D4) — `infra/terraform/` is a placeholder.
