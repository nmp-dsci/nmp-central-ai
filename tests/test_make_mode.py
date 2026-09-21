"""The Makefile keeps validation runs (CI, no-mistakes worktrees) off the live stack.

Run `make mode` — the same resolution `up`/`down` use — under each trigger and
assert the project it would drive; the live names are what every sibling joins.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
ISOLATE = (
    "CI",
    "NO_MISTAKES_GATE",
    "VALIDATION",
    "COMPOSE_PROJECT_NAME",
    "PLATFORM_NETWORK",
    "MLFLOW_PORT",
)


def mode(**extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in ISOLATE} | extra
    out = subprocess.run(
        ["make", "-s", "mode"], cwd=REPO, env=env, check=True, capture_output=True, text=True
    )
    return dict(kv.split("=", 1) for kv in out.stdout.split())


def test_a_plain_checkout_drives_the_live_stack() -> None:
    assert mode() == {
        "mode": "live",
        "project": "nmp-central",
        "network": "nmp-central",
        "mlflow": "http://localhost:5000",
    }


@pytest.mark.parametrize("trigger", ["CI", "NO_MISTAKES_GATE", "VALIDATION"])
def test_a_validation_trigger_gets_its_own_project_network_and_ports(trigger: str) -> None:
    got = mode(**{trigger: "1"})
    assert got["mode"] == "validation"
    assert got["project"] != "nmp-central" and got["network"] != "nmp-central"
    assert got["mlflow"] != "http://localhost:5000"


def test_validation_down_also_drops_its_volumes_and_live_down_keeps_them() -> None:
    def dry(**extra: str) -> str:
        env = {k: v for k, v in os.environ.items() if k not in ISOLATE} | extra
        return subprocess.run(
            ["make", "-n", "down"], cwd=REPO, env=env, check=True, capture_output=True, text=True
        ).stdout

    assert "-v" not in dry()
    assert "-v" in dry(VALIDATION="1")
