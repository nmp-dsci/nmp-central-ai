# s04 — a SQL frontend for the central Postgres (plan of record + receipt)

Status: decided and **built** 2026-09-22 on branch `sql-frontend` · Review artifact:
`.lavish/s02_sql-frontend.html` · Decisions D20–D24 in `AGENTS.md`.

## Goal

A browser page where a person can see every table in every project database (`mlflow`, `dab`,
`dataqa`) and run SQL, without building anything of our own and without anyone typing a host or
password into a UI.

## Survey (verified 2026-09-22 against Docker Hub tags and vendor docs)

| Option | Latest | Image (arm64) | Editor | Connections from env | Verdict |
|---|---|---|---|---|---|
| **DbGate Community** | 7.3.0 · 2026-09-15 · GPL-3 | 147 MB | full (autocomplete, tabs, kill, export, ER) | yes (`CONNECTIONS`, `SERVER_x` … `ALLOWED_DATABASES_x`, `READONLY_x`) | **chosen**; trial: 70 MB idle → 234 MB after DAB's 2 813 tables |
| pgweb | 0.17.0 · 2025-11-22 · MIT | 66 MB | basic, read-only grid | TOML bookmarks | fallback |
| CloudBeaver CE | 26.2.1 · Apache-2 | 416 MB | DBeaver-grade | partly (wizard) | overkill (JVM, mandatory login) |
| Adminer / AdminNeo | 6.0.1 / 5.8.0 | 43 / 62 MB | textarea | plugin | not an editor |
| pgAdmin 4 | monthly | 181 MB | query tool | servers.json + master password | admin-oriented |
| Desktop client | — | — | best | by hand | complement, not in the stack (none installed) |

## Decisions

| ID | Decision |
|----|----------|
| D20 | DbGate Community as compose service `dbgate`, image pinned. |
| D21 | Host port `5050`; validation mode `15050` (D12 rule). |
| D22 | One read-write connection per project database as `nmp` (D16), fenced with `ALLOWED_DATABASES`; rendered from the registry into `.dbgate.env`; `--dbgate-readonly` flips all to read-only; `ui_separate_schemas: true` on a database block turns on lazy schema loading (DAB). |
| D23 | No web login; published on `127.0.0.1` only. |
| D24 | DbGate's MCP server off; M4 decides the MCP surface. |

## What was built (receipt — every scope ID the reviewer submitted)

| ID | Item | Outcome |
|----|------|---------|
| S1 | compose service + port + validation mode + gitignore | **addressed** — `docker-compose.yml` service `dbgate` (`dbgate/dbgate:7.3.0`, `env_file: .dbgate.env` `required: false`, `127.0.0.1:${DBGATE_PORT:-5050}:3000`, node-based healthcheck, `depends_on: postgres`); Makefile exports `DBGATE_PORT` 5050 / 15050 and `DBGATE_URI`; `.env.example`; `.gitignore` `.dbgate.env`; `tests/test_make_mode.py` asserts the `dbui` line in both modes. |
| S2 | `render_dbgate_env` in `db_init.py` with tests | **addressed** — pure renderer (server from `postgres_uri_compose`, superuser + `POSTGRES_PASSWORD`, `ALLOWED_DATABASES`, optional `READONLY`, `USE_SEPARATE_SCHEMAS` from the registry's `ui_separate_schemas`); written on every `db-init` as `.dbgate.env`; CLI `--dbgate-out`, `--dbgate-readonly`; `Database.ui_separate_schemas`; registry P6 sets it; two tests parse the env the way compose does and assert one fenced superuser connection per database, no project role leaks, readonly and password override. |
| S3 | make `db-init` restart, `status` line, CI | **addressed** — `db-init` ends with `compose up -d --no-deps --force-recreate --wait dbgate`; `status` prints `dbui OK <url> (N connections)` or fails; `mode` and `up` print the URL; new `make db-ui`; CI `stack` job runs `make status` after `db-init`. |
| S4 | PLATFORM.md, runbook, README, skill | **addressed** — PLATFORM.md Postgres table row *Browse / query (humans)* + rule zero mentions the DB UI; AGENTS.md D20–D24; CLAUDE.md quick ref + port list; README quickstart/layout; `docs/runbooks/central-postgres.md` and `local-stack.md` rows; `platform-db` skill tells agents to point the human at it and keep using psql; plugin 0.2.1. |
| S5 | no-mistakes + PR, not merged | see the PR link in the chat report. |
| S6 | remove `dbgate-trial` | **addressed** — removed before the compose service took port 5050. |

## Verification

`make up` → four healthy containers; `make db-init` renders 3 connections and reloads the service;
`make status` → `dbui OK http://127.0.0.1:5050 (3 connections)`; the UI lists
`PLATFORM nmp-central-ai · mlflow`, `P5 data-qa-agent · dataqa`, `P6 dataagentbench · dab`, opens tables
and runs queries (trial query: `select current_user, count(*) from marts.property_sales` → `nmp · 827689`).
`make lint && make test` green (22 tests), `make plugin-validate` passes.

## Out of scope

Web login, MCP (M4), AWS (D19), editing through the UI as a project role (RLS would hide rows), a UI in a
sibling's compose file (rule zero).
