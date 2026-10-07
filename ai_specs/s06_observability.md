# s06 — observability: Langfuse alongside MLflow

Plan of record and build receipt for D33–D36. The review that produced it is
`.lavish/s04_observability-mlflow-vs-langfuse.html`.

## The question

Should MLflow be replaced by Langfuse for observability, self-hosted?

## The answer

**No — split the job.** Scored across 52 features (the union of both products, as self-hosted
OSS only) the two land almost level: MLflow 72% weighted, Langfuse 74%. That near-tie hides the
shape that matters:

| category | MLflow | Langfuse |
|---|---|---|
| A GenAI tracing & observability | 26/50 | **48/50** |
| B evaluation & scoring | 23/35 | **30/35** |
| C prompt lifecycle | 19/30 | **25/30** |
| D ML lifecycle (run & model ledger) | **40/40** | 9/40 |
| E self-hosting & operations | **29/40** | 26/40 |
| F governance & licensing | 16/35 | **21/35** |
| G ecosystem & portability | 23/30 | **27/30** |

Langfuse has no answer at all (score 0) for the model registry, model packaging, classic-ML
autologging and step-wise metric series, and scores 1 on a generic artifact store. A full swap
was rejected on two measured facts: **2 923 artifacts (81.9 MB of .json and .md evaluation
reports)** and **743 params** have nowhere to go.

### What measurement changed the answer

The expected blocker was step-wise metric curves, which Langfuse cannot represent. They are
unused: `max(step) = 0` across all 9 928 metric rows. The metrics here are flat scorecards,
which Langfuse *scores* can carry. The real blockers turned out to be the artifact store and
the params table — duller, and decisive.

### Measured baseline (2026-10-02, live stack)

| | |
|---|---|
| MLflow | 3.16.1 (current latest) |
| traces / spans | 1 480 / 26 279 |
| runs / experiments | 128 / 10 |
| metrics | 9 928 rows, 835 keys, **all step 0** |
| params / tags | 743 / 1 735 |
| registered models | 4, of which 2 are prompts (65 versions); 1 real model with 5 versions |
| artifacts | 2 923 objects, 81.9 MB — 1 728 .json, 1 029 .md, **no model binaries** |
| storage | 67 MB Postgres + 81.9 MB MinIO |
| code footprint | 64 files, 357 lines across 7 siblings |
| API mix | 30 `log_metric`, 23 `autolog`, 18 `log_artifact*`, 13 OTLP `/v1/traces`, 7 `@mlflow.trace`, 6 `search_runs` |

## Decisions

See AGENTS.md D33–D36. In short: observability splits from the ledger (D33); Langfuse is a
compose profile, not part of `make up` (D34); it consumes the cluster Postgres and MinIO like
any other tenant (D35); the registry says where each project's traces go (D36).

## Scope and status

| id | item | status |
|---|---|---|
| S1 | Measure host headroom against Langfuse's floor | **done** — `scripts/langfuse_doctor.py`, gates `langfuse-up` |
| S2 | Langfuse in compose, reusing Postgres + MinIO, host-only, validation ports | **done** — profile `langfuse`, not started |
| S3 | `observability:` block in the registry as source of truth | **done** — parser, validation, 12 tests |
| S4 | Move P5 data-qa's traces (parallel, reversible) | not started |
| S5 | Extend `make check` to prove traces land in Langfuse | not started |
| S6 | ClickHouse backup before cutover | not started |
| S7 | Document the split rule | **done** — PLATFORM.md rule 8, runbook, D33–D36 |
| S8 | Prompt migrator for the 65 versions | parked by decision |

## The blocker S1 found

Langfuse's floor is 4 cores / 16 GiB / 100 GiB. The host is comfortable (10 cores, 32 GiB), but
the **Docker VM is 7.7 GiB with 3.1 GiB already in use** — three of the doctor's four checks
fail. The VM size is a Docker Desktop setting, not a hardware limit, so this is a one-line fix
by the operator; until it is made, `make langfuse-up` refuses to start.

This is why S2 shipped as a profile rather than as part of `make up`: the definition is correct
and reviewable now, and nothing starts until the host can hold it.

## Open questions

- **Is the MLflow trace UI actually inadequate?** It scored 3 against Langfuse's 5 on feature
  surface, but 1 480 traces have been read in it. If it has been fine, the case for the whole
  migration weakens.
- **Does Databricks change the maths?** Managed MLflow supplies production monitoring (A8) and
  online eval (B4) — the two biggest Langfuse wins — without Langfuse at all.
