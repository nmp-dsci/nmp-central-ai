#!/usr/bin/env python
"""M1 verifier: prove each registered project can log to the central MLflow server.

For every project with a smoke command: record t0, run the smoke command inside the
project with MLFLOW_TRACKING_URI forced to the central server, then ask the server for
runs and/or traces in that project's experiments created after t0. One row per project,
non-zero exit if any project misses.

    uv run scripts/check_projects.py [--uri URI] [--only P1,P5] [--timeout 900]
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _registry import Project, load_registry, resolve_uri  # noqa: E402


def count_runs(client, exp_id: str, t0_ms: int) -> int:  # type: ignore[no-untyped-def]
    runs = client.search_runs(
        [exp_id], filter_string=f"attributes.start_time >= {t0_ms}", max_results=50
    )
    return len(runs)


def count_traces(client, exp_id: str, t0_ms: int) -> int:  # type: ignore[no-untyped-def]
    try:
        traces = client.search_traces(locations=[exp_id], max_results=50)
    except TypeError:  # older client signature
        traces = client.search_traces(experiment_ids=[exp_id], max_results=50)
    return sum(1 for t in traces if int(getattr(t.info, "timestamp_ms", 0) or 0) >= t0_ms)


def run_smoke(p: Project, uri: str, timeout: int) -> tuple[int, str]:
    env = dict(os.environ, MLFLOW_TRACKING_URI=uri)
    proc = subprocess.run(
        ["bash", "-lc", p.smoke],
        cwd=p.path,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    tail = (proc.stdout + proc.stderr).strip().splitlines()[-8:]
    return proc.returncode, "\n".join(tail)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--uri", default=None)
    ap.add_argument("--only", default="", help="comma-separated project ids")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    reg = load_registry()
    uri = resolve_uri(args.uri, reg)
    only = {s.strip() for s in args.only.split(",") if s.strip()}

    from mlflow import MlflowClient

    client = MlflowClient(tracking_uri=uri)
    print(f"central MLflow: {uri}\n")
    failures = 0
    for p in reg.projects:
        if only and p.id not in only:
            continue
        if not p.on_platform:
            print(f"  {p.id:<3} {p.name:<22} skip   ({p.status})")
            continue
        if p.status == "deferred" or not p.smoke:
            print(f"  {p.id:<3} {p.name:<22} skip   ({p.status}, no smoke)")
            continue
        if not p.path.exists():
            print(f"  {p.id:<3} {p.name:<22} FAIL   path missing: {p.path}")
            failures += 1
            continue

        t0 = int(time.time() * 1000) - 2000
        try:
            code, tail = run_smoke(p, uri, args.timeout)
        except subprocess.TimeoutExpired:
            code, tail = 124, "smoke timed out"

        exp_ids = []
        for name in p.experiments:
            exp = client.get_experiment_by_name(name)
            if exp is not None:
                exp_ids.append(exp.experiment_id)

        runs = sum(count_runs(client, e, t0) for e in exp_ids) if p.verify in {"runs", "both"} else -1
        traces = (
            sum(count_traces(client, e, t0) for e in exp_ids) if p.verify in {"traces", "both"} else -1
        )
        ok = code == 0 and (runs != 0) and (traces != 0)
        status = "PASS" if ok else "FAIL"
        if not ok:
            failures += 1
        detail = f"smoke={code} runs={runs if runs >= 0 else '-'} traces={traces if traces >= 0 else '-'}"
        print(f"  {p.id:<3} {p.name:<22} {status}   {detail}")
        if (not ok or args.verbose) and tail:
            print("        " + tail.replace("\n", "\n        "))

    print()
    if failures:
        print(f"{failures} project(s) failed")
        return 1
    print("all registered projects log to the central server")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
