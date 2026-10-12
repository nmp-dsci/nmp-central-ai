"""AWS demos sleep by pausing, never deleting, and their deploys are off while asleep (D37)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from _registry import AwsDemo, RegistryError, load_registry  # noqa: E402
from aws_demos import Demo, plan_sleep, plan_wake  # noqa: E402

BASE = {
    "platform": {
        "mlflow_uri": "http://localhost:5000",
        "mlflow_uri_compose": "http://mlflow:5000",
        "docker_network": "nmp-central",
    }
}
DEMO = {
    "apprunner": "convfinqa-demo",
    "region": "ap-southeast-1",
    "repo": "nmp-dsci/ConvFinQA-agent",
    "workflow": "deploy-aws.yml",
}


def write_registry(tmp_path: Path, projects: list[dict[str, object]]) -> Path:
    reg_dir = tmp_path / "registry"
    reg_dir.mkdir()
    p = reg_dir / "projects.yaml"
    p.write_text(yaml.safe_dump(BASE | {"projects": projects}))
    return p


def proj(pid: str, demo: object = None, *, declared: bool = True) -> dict[str, object]:
    out: dict[str, object] = {"id": pid, "name": pid.lower(), "path": "."}
    if declared:
        out["aws_demo"] = demo
    return out


def demo(status: str, workflow: str = "active", deploying: bool = False) -> Demo:
    d = Demo(pid="P1", demo=AwsDemo("convfinqa-demo", "ap-southeast-1", "o/r", "deploy-aws.yml"))
    d.status, d.workflow, d.deploying = status, workflow, deploying
    return d


# ---- registry -----------------------------------------------------------------


def test_the_registry_lists_only_projects_that_declare_a_demo(tmp_path: Path) -> None:
    reg = load_registry(write_registry(tmp_path, [proj("P1", DEMO), proj("P2", declared=False)]))
    assert [p.id for p in reg.aws_demos] == ["P1"]
    assert reg.by_id("P1").aws_demo == AwsDemo(
        "convfinqa-demo", "ap-southeast-1", "nmp-dsci/ConvFinQA-agent", "deploy-aws.yml"
    )


def test_a_demo_without_a_deploy_workflow_is_allowed(tmp_path: Path) -> None:
    raw = {"apprunner": "x-demo", "region": "us-east-1"}
    reg = load_registry(write_registry(tmp_path, [proj("P1", raw)]))
    d = reg.by_id("P1").aws_demo
    assert d is not None and d.workflow == "" and d.repo == ""


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (None, "App Runner service"),  # declared but empty is a typo, not an absence (D36)
        ({"region": "ap-southeast-1"}, "App Runner service"),
        (DEMO | {"region": "sydney"}, "AWS region"),
        (DEMO | {"workflow": ""}, "both `repo` and `workflow`"),
        (DEMO | {"repo": "ConvFinQA-agent"}, "owner/name"),
    ],
)
def test_an_incoherent_demo_block_is_refused(tmp_path: Path, raw: object, message: str) -> None:
    with pytest.raises(RegistryError, match=message):
        load_registry(write_registry(tmp_path, [proj("P1", raw)]))


def test_two_projects_cannot_claim_one_service(tmp_path: Path) -> None:
    """They would pause each other's demo."""
    with pytest.raises(RegistryError, match="declared by both P1 and P2"):
        load_registry(write_registry(tmp_path, [proj("P1", DEMO), proj("P2", DEMO)]))


def test_the_same_name_in_another_region_is_a_different_service(tmp_path: Path) -> None:
    other = DEMO | {"region": "ap-southeast-2"}
    reg = load_registry(write_registry(tmp_path, [proj("P1", DEMO), proj("P2", other)]))
    assert len(reg.aws_demos) == 2


def test_the_live_registry_declares_the_four_app_runner_demos() -> None:
    names = {p.aws_demo.service for p in load_registry().aws_demos if p.aws_demo}
    assert names == {"convfinqa-demo", "dabstep-demo", "yt-agent-demo", "data-qa-demo"}


# ---- plans ----------------------------------------------------------------------


def test_sleep_turns_deploys_off_before_pausing() -> None:
    """A deploy that lands on a paused service waits 20 minutes for RUNNING, then fails."""
    assert plan_sleep(demo("RUNNING")) == ["disable-workflow", "pause"]


def test_sleep_on_a_sleeping_demo_does_nothing() -> None:
    assert plan_sleep(demo("PAUSED", "disabled_manually")) == []


def test_sleep_still_turns_deploys_off_for_a_service_paused_by_hand() -> None:
    assert plan_sleep(demo("PAUSED")) == ["disable-workflow"]


def test_sleep_never_races_a_running_deploy() -> None:
    steps = plan_sleep(demo("RUNNING", deploying=True))
    assert len(steps) == 1 and steps[0].startswith("skip:")


@pytest.mark.parametrize("status", ["OPERATION_IN_PROGRESS", "ABSENT", "CREATE_FAILED"])
def test_sleep_skips_a_service_it_cannot_pause(status: str) -> None:
    assert plan_sleep(demo(status, "disabled_manually")) == [f"skip: service is {status}"]


def test_wake_resumes_before_it_turns_deploys_back_on() -> None:
    assert plan_wake(demo("PAUSED", "disabled_manually")) == ["resume", "enable-workflow"]


def test_wake_on_an_awake_demo_does_nothing() -> None:
    assert plan_wake(demo("RUNNING")) == []


def test_wake_leaves_a_demo_without_a_workflow_alone() -> None:
    assert plan_wake(demo("PAUSED", workflow="")) == ["resume"]


@pytest.mark.parametrize("status", ["OPERATION_IN_PROGRESS", "ABSENT"])
def test_wake_skips_a_service_it_cannot_resume(status: str) -> None:
    assert plan_wake(demo(status, "disabled_manually")) == [f"skip: service is {status}"]


def test_no_plan_ever_deletes() -> None:
    """D37: deleting gives the demo a new URL and risks App Runner's closed door."""
    for status in ["RUNNING", "PAUSED", "OPERATION_IN_PROGRESS", "ABSENT"]:
        for wf in ["active", "disabled_manually", ""]:
            for step in plan_sleep(demo(status, wf)) + plan_wake(demo(status, wf)):
                assert "delete" not in step
