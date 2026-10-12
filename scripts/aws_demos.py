#!/usr/bin/env python3
"""aws_demos.py — put the portfolio's always-on AWS demos to sleep, and wake them (D37).

Every project with an `aws_demo:` block in registry/projects.yaml has one App Runner
service and, usually, a GitHub workflow that deploys it.

    make demos-status                  each service's state and whether its deploys are on
    make demos-sleep                   disable the deploy workflow, then pause the service
    make demos-wake                    resume, wait for RUNNING, then re-enable the workflow
    ARGS="--only P1,P5 --dry-run"      limit to some projects / print the plan, change nothing

Sleep pauses and never deletes. A paused service keeps its URL and its image and bills no
compute; a deleted one comes back on a new URL, and App Runner closed to new customers on
2026-04-30. The workflow is disabled first because App Runner rejects deployments to a
paused service, and every deploy-aws.yml polls for RUNNING for 20 minutes before failing.

Credentials come from the environment: `aws sso login --profile <p>` and AWS_PROFILE=<p>.
`gh` must be logged in for the workflow step.

Exit codes: 0 done, 1 a step failed (each one is printed), 2 AWS is unreachable.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass

from _registry import AwsDemo, Project, load_registry

POLL_SECONDS = 15
SETTLING = "OPERATION_IN_PROGRESS"
ABSENT = "ABSENT"  # our marker: the registry names a service the account does not have
WORKFLOW_ON = "active"


@dataclass
class Demo:
    pid: str
    demo: AwsDemo
    arn: str = ""
    status: str = ABSENT
    url: str = ""
    workflow: str = ""  # gh state: active | disabled_manually | …; "" when none is declared
    deploying: bool = False  # a deploy run is in progress right now

    @property
    def label(self) -> str:
        return f"{self.pid} {self.demo.service} ({self.demo.region})"


# ---- plans: pure, so the tests can pin them -------------------------------------


def plan_sleep(d: Demo) -> list[str]:
    """Steps that take one demo to PAUSED with its deploys off. Empty means already asleep."""
    if d.deploying:
        return ["skip: a deploy is running; sleep again once it finishes"]
    if d.demo.workflow and d.workflow.startswith("unknown"):
        return [f"skip: deploy workflow state {d.workflow}; fix gh and retry"]
    steps: list[str] = []
    if d.workflow == WORKFLOW_ON:
        steps.append("disable-workflow")
    if d.status == "RUNNING":
        steps.append("pause")
    elif d.status not in {"PAUSED"}:
        steps.append(f"skip: service is {d.status}")
    return steps


def plan_wake(d: Demo) -> list[str]:
    """Steps that take one demo to RUNNING with its deploys on. Empty means already awake."""
    steps: list[str] = []
    if d.status == "PAUSED":
        steps.append("resume")
    elif d.status != "RUNNING":
        return [f"skip: service is {d.status}"]
    if d.workflow and d.workflow != WORKFLOW_ON:
        steps.append("enable-workflow")  # only once RUNNING, or the first deploy fails
    return steps


# ---- the outside world --------------------------------------------------------


def _run(cmd: list[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=True).stdout


def _err(e: subprocess.CalledProcessError) -> str:
    return (e.stderr or e.stdout or str(e)).strip().splitlines()[-1]


def aws_reachable() -> str | None:
    """None if credentials work, else the reason. Never prints the account id."""
    if not shutil.which("aws"):
        return "the aws CLI is not installed"
    try:
        _run(["aws", "sts", "get-caller-identity", "--output", "json"])
    except subprocess.CalledProcessError as e:
        return f"{_err(e)}\n  run `aws sso login --profile <profile>` and export AWS_PROFILE"
    return None


def read_service(d: Demo) -> None:
    token = ""
    while True:
        cmd = ["aws", "apprunner", "list-services", "--region", d.demo.region]
        cmd += ["--max-results", "20", "--output", "json"]
        if token:
            cmd += ["--next-token", token]
        page = json.loads(_run(cmd))
        for row in page.get("ServiceSummaryList", []):
            if row.get("ServiceName") == d.demo.service:
                d.arn, d.status = row["ServiceArn"], row["Status"]
                d.url = row.get("ServiceUrl") or ""
                return
        token = page.get("NextToken") or ""
        if not token:
            d.arn, d.status, d.url = "", ABSENT, ""
            return


def read_workflow(d: Demo) -> None:
    if not d.demo.workflow:
        return
    if not shutil.which("gh"):
        d.workflow = "unknown (gh not installed)"
        return
    try:
        rows = json.loads(
            _run(["gh", "workflow", "list", "-R", d.demo.repo, "--all", "--json", "path,state"])
        )
        runs = json.loads(
            _run(
                [
                    "gh",
                    "run",
                    "list",
                    "-R",
                    d.demo.repo,
                    "--workflow",
                    d.demo.workflow,
                    "--status",
                    "in_progress",
                    "--json",
                    "databaseId",
                ]
            )
        )
    except subprocess.CalledProcessError as e:
        d.workflow = f"unknown ({_err(e)})"
        return
    match = [r["state"] for r in rows if str(r["path"]).endswith("/" + d.demo.workflow)]
    d.workflow = match[0] if match else "missing"
    d.deploying = bool(runs)


def act(d: Demo, step: str) -> None:
    region = ["--region", d.demo.region]
    if step == "pause":
        _run(["aws", "apprunner", "pause-service", *region, "--service-arn", d.arn])
    elif step == "resume":
        _run(["aws", "apprunner", "resume-service", *region, "--service-arn", d.arn])
    elif step == "disable-workflow":
        _run(["gh", "workflow", "disable", d.demo.workflow, "-R", d.demo.repo])
    elif step == "enable-workflow":
        _run(["gh", "workflow", "enable", d.demo.workflow, "-R", d.demo.repo])
    else:
        raise ValueError(step)


def wait_for(demos: list[Demo], want: str, timeout: int) -> list[Demo]:
    """Poll until every demo leaves OPERATION_IN_PROGRESS; return the ones not at `want`."""
    deadline = time.monotonic() + timeout
    pending = list(demos)
    while pending and time.monotonic() < deadline:
        time.sleep(POLL_SECONDS)
        for d in list(pending):
            read_service(d)
            if d.status != SETTLING:
                pending.remove(d)
                print(f"  {d.label}: {d.status}")
    return [d for d in demos if d.status != want]


# ---- commands -------------------------------------------------------------------


def load(only: set[str]) -> list[Demo]:
    projects: list[Project] = load_registry().aws_demos
    if only:
        unknown = only - {p.id for p in projects}
        if unknown:
            sys.exit(f"--only names projects without an aws_demo block: {sorted(unknown)}")
        projects = [p for p in projects if p.id in only]
    demos = []
    for p in projects:
        assert p.aws_demo is not None
        demos.append(Demo(pid=p.id, demo=p.aws_demo))
    return demos


def status(demos: list[Demo]) -> int:
    print(f"  {'project':<44} {'service':<22} {'deploys':<18} url")
    for d in demos:
        flag = " (deploy running)" if d.deploying else ""
        print(f"  {d.label:<44} {d.status:<22} {(d.workflow or '-') + flag:<18} {d.url or '-'}")
    return 0


def run(demos: list[Demo], verb: str, dry_run: bool, wait: bool, timeout: int) -> int:
    plan = plan_sleep if verb == "sleep" else plan_wake
    failed: list[str] = []
    moved: list[Demo] = []
    late: list[Demo] = []  # wake: workflows to enable once the service is RUNNING
    for d in demos:
        steps = plan(d)
        if not steps:
            print(f"  {d.label}: already {'asleep' if verb == 'sleep' else 'awake'}")
            continue
        print(f"  {d.label}: {' -> '.join(steps)}{'   (dry run)' if dry_run else ''}")
        if dry_run:
            continue
        for step in steps:
            if step.startswith("skip:"):
                failed.append(f"{d.label}: {step[6:]}")
                break
            if step == "enable-workflow" and d.status != "RUNNING":
                late.append(d)
                continue
            try:
                act(d, step)
            except subprocess.CalledProcessError as e:
                failed.append(f"{d.label}: {step} failed: {_err(e)}")
                break
            if step in {"pause", "resume"}:
                d.status = SETTLING
                moved.append(d)
    if moved and wait:
        want = "PAUSED" if verb == "sleep" else "RUNNING"
        print(f"waiting for {want} (up to {timeout}s) …")
        for d in wait_for(moved, want, timeout):
            failed.append(f"{d.label}: still {d.status}, wanted {want}")
    for d in late:
        if d.status != "RUNNING":
            if not wait:
                print(
                    f"  {d.label}: deploys stay off until the service is RUNNING; "
                    "re-run `make demos-wake` to enable them"
                )
                continue
            failed.append(f"{d.label}: deploys left off because the service is {d.status}")
            continue
        try:
            act(d, "enable-workflow")
            print(f"  {d.label}: deploys enabled")
        except subprocess.CalledProcessError as e:
            failed.append(f"{d.label}: enable-workflow failed: {_err(e)}")
    if verb == "wake" and moved and not dry_run:
        print(
            "note: resume restores the image that was live before the pause. If main moved on,\n"
            "      run the deploy once: gh workflow run <workflow> -R <repo>"
        )
    for f in failed:
        print(f"FAIL {f}", file=sys.stderr)
    return 1 if failed else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("verb", choices=["status", "sleep", "wake"])
    ap.add_argument("--only", default="", help="comma-separated project ids, e.g. P1,P5")
    ap.add_argument("--dry-run", action="store_true", help="print the plan; change nothing")
    ap.add_argument("--no-wait", action="store_true", help="do not wait for PAUSED / RUNNING")
    ap.add_argument("--timeout", type=int, default=900, help="seconds to wait (default 900)")
    args = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[union-attr]  # waits are minutes long

    demos = load({s.strip() for s in args.only.split(",") if s.strip()})
    if not demos:
        print("no aws_demo blocks in the registry")
        return 0
    reason = aws_reachable()
    if reason:
        print(f"AWS unreachable: {reason}", file=sys.stderr)
        return 2
    for d in demos:
        read_service(d)
        read_workflow(d)
    if args.verb == "status":
        return status(demos)
    return run(demos, args.verb, args.dry_run, not args.no_wait, args.timeout)


if __name__ == "__main__":
    sys.exit(main())
