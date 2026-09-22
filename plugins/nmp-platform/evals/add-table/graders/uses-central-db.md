---
type: llm
weight: 2
---

You are judging whether the response respects the shared-platform rule: the portfolio has ONE central Postgres server and each project has ONE database on it (DataAgentBench's is `dab`).

PASS if the response (a) puts the new table inside the project's existing database on the central server — it mentions the `dab` database, or `localhost:5432` / `postgres:5432`, or getting the URL from `make db-urls` / `.db-urls.env` / the project's `.env` DATABASE_URL — AND (b) describes the reset as dropping/recreating the project's own schema(s) inside its own database (e.g. `DROP SCHEMA dataagentbench CASCADE` then re-run roles.sql / migrations / ingest), AND (c) does none of the FAIL items. Mentioning a backup first (`make db-backup`) or a platform health check is a plus but not required.

FAIL if it proposes adding a postgres/db service to the project's docker-compose, uses port 5433 or 5434, creates a brand-new database or cluster for the table, hardcodes a database URL or password, or resets via `DROP DATABASE` or `docker compose down -v`.

Ignore any preamble about tools being unavailable; judge only the plan/commands given.
