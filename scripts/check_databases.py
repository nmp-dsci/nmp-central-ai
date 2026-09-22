#!/usr/bin/env python
"""M3 verifier: prove each registered project's database exists, its roles connect, and its
own zero-LLM smoke passes against the central Postgres.

For every project with a `database:` block: connect as the superuser and check the
database and its extensions; connect as each declared role; then run the project's
`smoke` command inside the project with its URLs exported (the same values db_init
writes to .db-urls.env). One row per project, non-zero exit on any miss.

    uv run scripts/check_databases.py [--base-uri postgresql://localhost:5432]
                                      [--mlflow-uri http://localhost:5000] [--only P5,P6]
                                      [--timeout 600]
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _registry import SUPERUSER, Project, Registry, load_registry, resolve_uri  # noqa: E402
from db_init import url_for  # noqa: E402


def query(url: str, sql: str) -> list[tuple[object, ...]]:
    import psycopg

    with psycopg.connect(url, connect_timeout=5) as conn:
        return [tuple(r) for r in conn.execute(sql).fetchall()]


def check_project(
    reg: Registry, p: Project, base: str, mlflow_uri: str, timeout: int
) -> tuple[bool, str, str]:
    """Return (ok, detail, tail-of-smoke-output)."""
    db = p.database
    assert db is not None
    notes: list[str] = []
    ok = True

    su_url = url_for(reg, db, SUPERUSER, "postgresql", base)
    try:
        have = {str(r[0]) for r in query(su_url, "select extname from pg_extension")}
    except Exception as exc:  # noqa: BLE001 - any connection error is a FAIL row
        return False, f"superuser connect failed: {type(exc).__name__}: {str(exc).strip()[:90]}", ""
    missing = [e for e in db.extensions if e not in have]
    if missing:
        ok = False
        notes.append(f"ext missing={','.join(missing)}")
    else:
        notes.append(f"ext={','.join(db.extensions) or '-'}")

    bad_roles = []
    for role in db.roles:
        try:
            query(url_for(reg, db, role, "postgresql", base), "select 1")
        except Exception as exc:  # noqa: BLE001
            bad_roles.append(f"{role}({type(exc).__name__})")
    if bad_roles:
        ok = False
        notes.append("roles failed=" + ",".join(bad_roles))
    else:
        notes.append(f"{len(db.roles)} role{'s' if len(db.roles) != 1 else ''} ok")

    tail = ""
    if db.smoke:
        env = dict(os.environ, MLFLOW_TRACKING_URI=mlflow_uri)
        for e in db.env:
            env[e.var] = url_for(reg, db, e.role, e.scheme, base)
        try:
            proc = subprocess.run(
                ["bash", "-lc", db.smoke],
                cwd=p.path,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            code = proc.returncode
            tail = "\n".join((proc.stdout + proc.stderr).strip().splitlines()[-8:])
        except subprocess.TimeoutExpired:
            code, tail = 124, "smoke timed out"
        notes.append(f"smoke={code}")
        ok = ok and code == 0
    else:
        notes.append("smoke=-")
    return ok, "  ".join(notes), tail


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--base-uri",
        default=None,
        help="host-side base URI (default: env PLATFORM_POSTGRES_URI or registry)",
    )
    ap.add_argument(
        "--mlflow-uri",
        default=None,
        help="MLflow tracking URI for smoke commands that talk to MLflow, e.g. PLATFORM "
        "(default: env MLFLOW_TRACKING_URI or registry)",
    )
    ap.add_argument("--only", default="", help="comma-separated project ids")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    reg = load_registry()
    base = args.base_uri or os.environ.get("PLATFORM_POSTGRES_URI") or reg.postgres_uri
    mlflow_uri = resolve_uri(args.mlflow_uri, reg)
    only = {s.strip() for s in args.only.split(",") if s.strip()}
    print(f"central Postgres: {base}\n")

    failures = 0
    for p in reg.databases:
        if only and p.id not in only:
            continue
        db = p.database
        assert db is not None
        label = f"  {p.id:<8} {p.name:<18} db={db.name:<8}"
        if db.status != "migrated":
            print(f"{label} skip   ({db.status})")
            continue
        if not p.path.exists():
            print(f"{label} FAIL   path missing: {p.path}")
            failures += 1
            continue
        ok, detail, tail = check_project(reg, p, base, mlflow_uri, args.timeout)
        print(f"{label} {'PASS' if ok else 'FAIL'}   {detail}")
        if (not ok or args.verbose) and tail:
            print("        " + tail.replace("\n", "\n        "))
        failures += 0 if ok else 1

    print()
    if failures:
        print(f"{failures} database(s) failed")
        return 1
    print("all registered databases live on the central server")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
