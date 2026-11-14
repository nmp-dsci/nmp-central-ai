#!/usr/bin/env python3
"""dsh_doctor.py — install, check and launch DeepSeek Harness from this repo (D39).

    make dsh-install            copy agent/dsh/ into ~/.dsh (refuses an edited copy unless FORCE=1)
    make dsh-doctor             versions, pnpm, key stored, every DeepSeek upload off, MLflow up
    make dsh-tui DIR=../repo    guard, then start dsh-TUI in DIR with a clean environment
    make dsh-web / dsh-run      the same for the browser UI and one headless task

By default dsh uploads to DeepSeek in three ways: the session log on every API request,
the session log to an OTel collector whenever you give feedback, and the list of installed
plugins. agent/dsh/home.cordis.patch.yml turns all three off. The guard reads each profile's
*composed* config (`dsh --profile P --dump-config`) and refuses to launch unless they are
still off, because a dsh or dsh-TUI upgrade can rename or re-default a row.

The agent's shell inherits every environment variable except dsh's own DSH_* ones, so the
launcher starts dsh from an empty environment (`env -i`) plus the few variables below.

Exit codes: 0 ok, 1 a check failed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
PORTFOLIO = ROOT.parent
SRC = ROOT / "agent" / "dsh"
INSTALLS = {"home.cordis.patch.yml": "cordis.patch.yml", "AGENTS.md": "AGENTS.md"}
PROFILES = ("dsh-tui", "web", "headless")
TUI_PACKAGE = "@deepseek-harness-tui/dsh-tui"
MIN_NODE = (24, 9)
SESSION_FORMATS = {4}  # what scripts/dsh_log.py reads

# package name -> (config key, the only value that keeps it from uploading)
UPLOADS: dict[str, tuple[str, object]] = {
    "@deepseek-ai/dsh-session-log-deepseek": ("enabled", False),
    "@deepseek-ai/dsh-session-telemetry-otel": ("mode", "DISABLED"),
    "@deepseek-ai/dsh-plugin-package-inventory-deepseek": ("enabled", False),
}
# Variables the launcher passes through; everything else (API keys included) stays behind.
PASS_THROUGH = ("HOME", "PATH", "LANG", "TERM", "COLORTERM", "TERM_PROGRAM", "TMPDIR")
LAUNCH_ENV = {
    "DSH_TELEMETRY_MODE": "DISABLED",  # belt and braces: the base row reads this too
    "DSH_TELEMETRY_DISABLED": "1",  # dsh disables the OTel row outright when this is set
    "DSH_TUI_UPDATE_ENGINE": "0",  # stop dsh-TUI's /update moving the pinned dsh
    "DSH_TUI_UPDATE_LAUNCHER": "0",
}


def dsh_home() -> Path:
    home = os.environ.get("DSH_HOME", "").strip()
    return Path(home).expanduser() if home else Path.home() / ".dsh"


def clean_env(base: dict[str, str] | None = None) -> dict[str, str]:
    """The launcher's whole environment: a short allow-list plus the dsh switches."""
    src = os.environ if base is None else base
    env = {k: src[k] for k in PASS_THROUGH if src.get(k)}
    env.setdefault("LANG", "en_AU.UTF-8")
    return env | LAUNCH_ENV


# ---- pure checks: the tests pin these ------------------------------------------


class JsExpr(str):
    """A `!!js` value from a dump; dsh evaluates it at boot, so it proves nothing here."""


class _DumpLoader(yaml.SafeLoader):
    pass


def _js(loader: yaml.SafeLoader, node: yaml.Node) -> JsExpr:
    return JsExpr(loader.construct_scalar(node))  # type: ignore[arg-type]


_DumpLoader.add_constructor("tag:yaml.org,2002:js", _js)


def parse_dump(text: str) -> list[dict[str, Any]]:
    rows = yaml.load(text, Loader=_DumpLoader)
    if not isinstance(rows, list):
        raise ValueError("dsh --dump-config did not print a list of rows")
    return [r for r in rows if isinstance(r, dict)]


def upload_findings(rows: list[dict[str, Any]]) -> list[str]:
    """Every row that could still upload to DeepSeek. Empty means all three are off."""
    found: list[str] = []
    for row in rows:
        name = str(row.get("name", ""))
        if name not in UPLOADS or row.get("disabled") is True:
            continue
        key, want = UPLOADS[name]
        got = (row.get("config") or {}).get(key)
        if isinstance(got, JsExpr) or got != want:
            found.append(f"{row.get('id', '?')} ({name}): {key} is {got!r}, needs {want!r}")
    return found


def in_portfolio(path: Path, portfolio: Path = PORTFOLIO) -> bool:
    try:
        path.resolve().relative_to(portfolio.resolve())
    except ValueError:
        return False
    return True


def node_ok(version: str) -> bool:
    m = re.match(r"v?(\d+)\.(\d+)", version.strip())
    return m is not None and (int(m.group(1)), int(m.group(2))) >= MIN_NODE


def install_plan(src: Path, dst: Path, force: bool) -> list[tuple[Path, Path, str]]:
    """(source, target, action) per file: copy, same or refuse (an edited copy)."""
    plan = []
    for name, target in INSTALLS.items():
        s, d = src / name, dst / target
        if not d.exists():
            action = "copy"
        elif d.read_bytes() == s.read_bytes():
            action = "same"
        else:
            action = "copy" if force else "refuse"
        plan.append((s, d, action))
    return plan


# ---- the outside world ---------------------------------------------------------


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def _out(cmd: list[str], env: dict[str, str] | None = None, cwd: Path | None = None) -> str:
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=120, check=True, env=env, cwd=cwd
    ).stdout


def dsh_version() -> str:
    if not shutil.which("dsh"):
        return "missing"
    try:
        return _out(["dsh", "--version"]).strip()
    except subprocess.CalledProcessError:
        return "unknown"


def tui_version() -> str:
    pkg = dsh_home() / "profiles" / "dsh-tui" / "node_modules" / TUI_PACKAGE / "package.json"
    if not pkg.is_file():
        return "missing"
    return str(json.loads(pkg.read_text()).get("version", "unknown"))


def profile_findings(profile: str) -> list[str]:
    try:
        text = _out(["dsh", "--profile", profile, "--dump-config"], env=clean_env(), cwd=ROOT)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        return [f"could not compose the {profile} profile: {e}"]
    return upload_findings(parse_dump(text))


def guard(dsh_pin: str, tui_pin: str, profiles: tuple[str, ...]) -> list[str]:
    problems = []
    if (v := dsh_version()) != dsh_pin:
        problems.append(f"dsh is {v}, pinned {dsh_pin}: run `make dsh-install`")
    if "dsh-tui" in profiles and (v := tui_version()) != tui_pin:
        problems.append(f"dsh-TUI is {v}, pinned {tui_pin}: run `make dsh-install`")
    for p in profiles:
        problems += [f"{p}: {f}" for f in profile_findings(p)]
    return problems


def session_formats(root: Path) -> dict[int, int]:
    counts: dict[int, int] = {}
    for f in root.glob("*/*/session.v*.jsonl*"):
        m = re.search(r"session\.v(\d+)\.jsonl", f.name)
        if m:
            counts[int(m.group(1))] = counts.get(int(m.group(1)), 0) + 1
    return counts


def mlflow_up() -> tuple[bool, str]:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _registry import load_registry, resolve_uri

    uri = resolve_uri(None, load_registry())
    try:
        with urllib.request.urlopen(f"{uri}/health", timeout=5) as r:
            return r.status == 200, uri
    except OSError:
        return False, uri


# ---- commands --------------------------------------------------------------------


def cmd_install(force: bool) -> int:
    home = dsh_home()
    home.mkdir(parents=True, exist_ok=True)
    plan = install_plan(SRC, home, force)
    refused = [d for _, d, a in plan if a == "refuse"]
    if refused:
        for d in refused:
            print(f"{d} was edited by hand; edit agent/dsh/ instead, or re-run with FORCE=1")
        return 1
    for s, d, action in plan:
        if action == "copy":
            shutil.copyfile(s, d)
        print(f"  {'installed' if action == 'copy' else 'unchanged'}  {d}")
    return 0


def cmd_check(dsh_pin: str, tui_pin: str) -> int:
    home = dsh_home()
    node = _out(["node", "--version"]).strip() if shutil.which("node") else "missing"
    checks = [
        Check("node", node_ok(node), f"{node} (needs >= {MIN_NODE[0]}.{MIN_NODE[1]})"),
        Check("pnpm", bool(shutil.which("pnpm")), shutil.which("pnpm") or "missing: npm i -g pnpm"),
        Check("dsh", dsh_version() == dsh_pin, f"{dsh_version()} (pinned {dsh_pin})"),
        Check("dsh-TUI", tui_version() == tui_pin, f"{tui_version()} (pinned {tui_pin})"),
    ]
    plan = install_plan(SRC, home, force=False)
    stale = [d.name for _, d, a in plan if a != "same"]
    checks.append(
        Check(
            "home patch",
            not stale,
            "installed" if not stale else f"run make dsh-install ({', '.join(stale)})",
        )
    )
    creds = home / ".credentials.yaml"
    checks.append(
        Check(
            "API key",
            creds.is_file(),
            "stored by dsh"
            if creds.is_file()
            else "not stored yet: start make dsh-tui and use /provider",
        )
    )
    for p in PROFILES:
        found = profile_findings(p)
        checks.append(
            Check(f"uploads ({p})", not found, "all off" if not found else "; ".join(found))
        )
    formats = session_formats(home / "sessions")
    odd = {v: n for v, n in formats.items() if v not in SESSION_FORMATS}
    checks.append(
        Check(
            "sessions",
            not odd,
            f"{sum(formats.values())} on disk" + (f"; unreadable formats {odd}" if odd else ""),
        )
    )
    up, uri = mlflow_up()
    checks.append(Check("mlflow", up, uri if up else f"{uri} unreachable: make up"))
    for c in checks:
        print(f"  {'ok  ' if c.ok else 'FAIL'}  {c.name:<18} {c.detail}")
    return 0 if all(c.ok for c in checks) else 1


def cmd_launch(profile: str, workdir: Path, dsh_pin: str, tui_pin: str, app_args: list[str]) -> int:
    if not in_portfolio(workdir):
        print(f"refusing {workdir}: dsh runs only inside {PORTFOLIO} (D39)", file=sys.stderr)
        return 1
    problems = guard(dsh_pin, tui_pin, (profile,))
    if problems:
        for p in problems:
            print(f"FAIL {p}", file=sys.stderr)
        print("not launching: fix the above, then `make dsh-doctor`", file=sys.stderr)
        return 1
    os.chdir(workdir)
    dsh = shutil.which("dsh") or "dsh"
    os.execve(dsh, [dsh, "--profile", profile, *app_args], clean_env())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    inst = sub.add_parser("install")
    inst.add_argument("--force", action="store_true")
    for name in ("check", "launch"):
        p = sub.add_parser(name)
        p.add_argument("--dsh", required=True, help="pinned dsh version")
        p.add_argument("--tui", required=True, help="pinned dsh-TUI version")
        if name == "launch":
            p.add_argument("profile", choices=PROFILES)
            p.add_argument("--dir", default=".", type=Path)
            p.add_argument("app_args", nargs=argparse.REMAINDER)
    args = ap.parse_args()
    if args.cmd == "install":
        return cmd_install(args.force)
    if args.cmd == "check":
        return cmd_check(args.dsh, args.tui)
    extra = [a for a in args.app_args if a != "--"]
    return cmd_launch(args.profile, args.dir, args.dsh, args.tui, extra)


if __name__ == "__main__":
    sys.exit(main())
