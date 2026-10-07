#!/usr/bin/env python3
"""langfuse_doctor.py — is this host big enough to run Langfuse? (S1, D33)

Langfuse's own docs recommend 4 cores / 16 GiB / 100 GiB disk. On a Mac the
number that actually binds is not the host's RAM but the Docker VM's, because
every container shares it — and `make up` has already spent some of it.

    make langfuse-doctor          report
    make langfuse-doctor --gate   exit 1 if the VM is too small (used by langfuse-up)

Exit codes: 0 fine, 1 too small (only with --gate), 2 could not measure.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass

GIB = 1024**3

# Langfuse's documented floor for a single-node deployment.
WANT_CORES = 4
WANT_RAM_GIB = 16.0
WANT_DISK_GIB = 100.0

# What the four new containers need in practice: ClickHouse alone reserves a
# few GiB, and the two Node services are ~1 GiB each.
NEED_FREE_GIB = 5.0


@dataclass(frozen=True)
class Docker:
    cores: int
    ram_gib: float
    used_gib: float

    @property
    def free_gib(self) -> float:
        return self.ram_gib - self.used_gib


def _run(cmd: list[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=True).stdout


def docker_capacity() -> Docker | None:
    """The VM's size, and what the running containers are already holding."""
    if not shutil.which("docker"):
        return None
    try:
        info = json.loads(_run(["docker", "info", "--format", "{{json .}}"]))
        cores, ram = int(info["NCPU"]), float(info["MemTotal"]) / GIB
    except (subprocess.SubprocessError, ValueError, KeyError):
        return None
    used = 0.0
    try:
        stats = _run(["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}"])
        for line in stats.splitlines():
            if "/" not in line:
                continue
            used += _to_gib(line.split("/")[0].strip())
    except subprocess.SubprocessError:
        pass  # a report without the in-use figure is still worth printing
    return Docker(cores=cores, ram_gib=ram, used_gib=used)


def _to_gib(value: str) -> float:
    """`1.305GiB` / `762.4MiB` / `576KiB` -> GiB."""
    for suffix, factor in (("GiB", 1.0), ("MiB", 1 / 1024), ("KiB", 1 / 1024**2), ("B", 1 / GIB)):
        if value.endswith(suffix):
            try:
                return float(value[: -len(suffix)]) * factor
            except ValueError:
                return 0.0
    return 0.0


def disk_free_gib(path: str = "/") -> float:
    return shutil.disk_usage(path).free / GIB


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gate", action="store_true", help="exit 1 when Langfuse would not fit")
    args = ap.parse_args()

    dk = docker_capacity()
    if dk is None:
        print("langfuse-doctor: docker is not available, cannot measure", file=sys.stderr)
        return 2

    disk = disk_free_gib()
    verdicts: list[tuple[bool, str]] = [
        (dk.cores >= WANT_CORES, f"docker cores      {dk.cores:>6d}        want >= {WANT_CORES}"),
        (
            dk.ram_gib >= WANT_RAM_GIB,
            f"docker VM memory  {dk.ram_gib:>6.1f} GiB    want >= {WANT_RAM_GIB:.0f} GiB",
        ),
        (
            dk.free_gib >= NEED_FREE_GIB,
            f"  of which free   {dk.free_gib:>6.1f} GiB    want >= {NEED_FREE_GIB:.0f} GiB "
            f"({dk.used_gib:.1f} GiB already in use)",
        ),
        (
            disk >= WANT_DISK_GIB,
            f"host disk free    {disk:>6.1f} GiB    want >= {WANT_DISK_GIB:.0f} GiB",
        ),
    ]

    print("Langfuse needs 4 cores / 16 GiB / 100 GiB (its own documented floor).\n")
    for ok, line in verdicts:
        print(f"  {'ok  ' if ok else 'FAIL'}  {line}")

    blockers = [line for ok, line in verdicts if not ok]
    if not blockers:
        print("\nthis host can run Langfuse.")
        return 0

    print(f"\n{len(blockers)} check(s) failed. The Docker VM is the usual culprit, and it is")
    print("a setting, not a hardware limit: Docker Desktop > Settings > Resources >")
    print("Memory. Raise it (the host has more), then re-run `make langfuse-doctor`.")
    if args.gate:
        print("\nrefusing to start Langfuse. Override deliberately with `make langfuse-up GATE=0`.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
