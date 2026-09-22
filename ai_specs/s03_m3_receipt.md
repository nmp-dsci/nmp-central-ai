# s03 — M3 build receipt (one Postgres for the portfolio)

Built 2026-09-22 from `ai_specs/s02_m3_central_db.md` (review artifact `.lavish/s01_m3-central-db-plan.html`).
Every ID the reviewer submitted in the scope batch has exactly one outcome below.

| ID | Item | Outcome |
|----|------|---------|
| M3.0 | Platform primitives in nmp-central-ai | **addressed** — PR #3 (`m3/platform-db`, no-mistakes green, merged): registry `database:` blocks incl. `PLATFORM` (mlflow) and `P6`; `scripts/_registry.py` Database/DbEnv + cluster-global name validation; `scripts/db_init.py` (idempotent roles / databases / extensions, `.db-urls.env`); `scripts/check_databases.py` wired into `make check`; make `db-init` `db-urls` `db-check` `db-psql` `db-backup` `db-restore`; compose D17 flags + `./backups` mount; `PLATFORM.md` Postgres table + rule 7; `AGENTS.md` D13–D19; `CLAUDE.md`; README; `docs/runbooks/central-postgres.md`; plugin skill `platform-db` + eval `add-table` (1.00 with, 0.00 without); CI runs `db-init` twice + `db-check --only PLATFORM`; `tests/test_db_init.py`. Follow-ups landed in PR #4 (`db-restore ROLE=`) and PR #5 (registry role `password` / `options` / `settings`, `db-restore SKIP= NO_PRIVS=`; the pipeline also corrected PLATFORM.md's password line). |
| P6 | DataAgentBench → central Postgres db `dab` | **addressed** — six steps done. Dump `-n dataagentbench` from `dab-postgres-1` (1.7 GB compressed, 3 min); restore `-j4` into `dab` in **1 m 28 s** (D17 flags); ownership handed to `dab_owner` (hence `db-restore ROLE=`); `roles.sql` ran unchanged. Proof: 2 813 tables both sides, sizes 6 653 MB → 6 804 MB (+2.3 %, fresh restore), row counts equal on the five largest tables, `make db-smoke` PASS (agent read-only, owner writes), `DAB_TEST_PG=1 pytest tests/test_roles.py` green, regenerated context packs (`dab context build --datasets agnews`) **byte-identical** to the committed ones. Cut over: `config.py` defaults → `localhost:5432/dab`, `infra/docker-compose.yml` + `infra/registry.P6.yaml` deleted, Makefile `platform-up` / `db-roles` / `db-smoke` / `db-reset`, docs. Old container **and 11 GB volume deleted**, port 5433 free. DataAgentBench commit `c57e62e` sits on its working branch `agent-build-v0` (9 unpushed commits of yours ahead of main — pushing that branch is your call). Central: PR #4 merged, `make check` P6 database row PASS. |
| P5 | data-qa-agent → central Postgres db `dataqa` | **addressed** — all six steps done. Code: data-qa PR #46 (branch `platform/central-postgres`, built in a worktree from `main` while your `demo-dbless` work was in flight, no-mistakes green incl. two pipeline fixes — `--entrypoint python` on the schema-level `reset`, and `CREATE DATABASE` in its own psql call in CI — squash-merged as `47c826f` after your #45): compose without a `db` service or `dbdata` volume, hosts `postgres:5432`, admin = `nmp` (D16), `make up` preflights the platform, schema-level `reset`, `scripts/db_smoke.py`, CI service container (D18), dbt/run.py defaults, docs. Data: dump of the live 2.3 GB database (34 s), restore into `dataqa` (16 s; `SKIP="DEFAULT ACL"` then `ALTER DEFAULT PRIVILEGES … FOR nmp`), redone fresh at cut-over; grants identical (app_user 102 / agent_ro 18 / admin_ro 44), 16 RLS policies both sides, row counts equal on six tables incl. `app.events` 177 716, Alembic at `0039_eval_loop_s49`; role attributes (`admin_ro BYPASSRLS`, `statement_timeout` 15 s/15 s/30 s) re-created from the registry. Cut-over: stack down, fresh dump/restore, `make up` → migrate ran, dbt build PASS=52, backend + agent healthy; live API as user1 sees 827 689 `marts.property_sales` rows and user2 sees 0 (RLS), `query_runs` rows landed centrally. Old `data-qa-agent-db-1` **and 3.5 GB volume deleted**, port 5434 free. Follow-up PR: `make db-smoke` defaults its URLs so it runs standalone. |
| P1-traces | ConvFinQA `.traces/traces.db` stays embedded SQLite | **deferred by decision** — recorded in s02 "Out of scope"; nothing changed in ConvFinQA. |
| HYGIENE | Daemon hygiene | **listed for your confirmation, nothing deleted** — see the table below. |

## Daemon hygiene — candidates (you confirm each; nothing has been deleted)

| Item | Size | Why it is a candidate |
|------|------|------------------------|
| `floor-plan-studio-db-1`, `-backend-api-1`, `-plan-agent-1`, `-frontend-1` containers + volume `floor-plan-studio_dbdata` | 49 MB | floor-plan-reviewer retired (review decision) |
| `kb-pg` container + its anonymous volume `39b55c92…` | 49 MB | unknown project, stopped 8 weeks |
| `01kxx3cfwtt7zaftcsky17nskk_dbdata` (53 MB), `01kyyd8eprjz6d72adebnsn74y_dbdata` (71 MB) + their `_dbt_target` | ≈130 MB | data-qa `.claude/worktrees` compose runs; no container uses them |
| `01kx89…`, `01kxzs…`, `01kyxny…`, `01kz7q…` `_dbdata` / `_dbt_target` | 0 B | empty leftovers of the same |
| `data-qa-agent_pgdata` | 71 MB | orphan from before data-qa's volume was renamed to `dbdata` (June) |
| 17 anonymous volumes 48–186 MB (`docker system df -v`) | ≈1.6 GB | not attributable from here; `docker volume prune` removes only the unreferenced ones |

`docker volume rm <name>` per line, or `docker volume prune` for the anonymous set once the named ones are gone.

## Verification

`make check` on 2026-09-22 after the cut-over: MLflow rows P1 P2 P3 P5 P6 PASS, P4 skip (deferred);
database rows PLATFORM, P5, P6 PASS. `docker ps` shows exactly one Postgres container
(`nmp-central-postgres-1`). Ports 5433 and 5434 are free. Central PRs #3 #4 #5 merged; data-qa PR #46
merged; DataAgentBench commit `c57e62e` on `agent-build-v0` (yours to push).

## Learned while building (already in the runbook / registry)

- `pg_restore --no-owner` hands everything to `nmp`; a project whose own role owns and writes to its
  schema (DAB's `dab_owner`) needs `ROLE=<role>` or it can no longer create tables.
- A dump from a server whose superuser had another name carries `ALTER DEFAULT PRIVILEGES FOR ROLE
  <old>` entries that cannot apply: `SKIP="DEFAULT ACL"` and recreate them for `nmp`.
- Role attributes (`BYPASSRLS`, `ALTER ROLE … SET statement_timeout`) are cluster-level and are not in
  a database dump; the registry now declares them (`options`, `settings`) so `db-init` recreates them.
- Grants restore fine when the roles pre-exist, so `--no-privileges` is opt-in (`NO_PRIVS=1`).
