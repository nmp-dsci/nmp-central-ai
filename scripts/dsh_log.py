#!/usr/bin/env python3
"""dsh_log.py — copy DeepSeek Harness sessions into the central MLflow (D39).

    make dsh-log                     log every finished turn not logged yet
    make dsh-log ARGS="--dry-run"    print what would be logged; write nothing
    uv run scripts/dsh_log.py --fixture tests/fixtures/dsh    the registry smoke (no model calls)

dsh writes one append-only log per session, ~/.dsh/sessions/--<cwd>--/<id>/session.v4.jsonl.
Each session becomes one run in experiment dsh/sessions: the ledger of tokens, cost and
counts. Each finished turn becomes one trace: your message, an LLM span per model call and
a TOOL span per tool call. Token counts are the provider usage dsh recorded on each call.

What never reaches MLflow (PLATFORM.md rules 3 and 4):
  - sessions whose working directory is outside ~/git/nmp-ai-portfolio;
  - reasoning text, attachments, and injected context (system prompt, instructions, skills);
  - the result of any tool call that names a credential file (.env*, *.pem, credentials);
  - secret values: every value in ~/.env and anything shaped like a key becomes [redacted];
and every logged text is cut to 4 KB.

A re-run starts after the last event already logged (run tag dsh.through_seq), so it is safe
to run as often as you like. A turn still in progress waits for the next run.

Exit codes: 0 ok, 1 a session could not be read (each is printed), 2 MLflow unreachable.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import uuid
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _registry import load_registry, resolve_uri  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PORTFOLIO = ROOT.parent
FORMATS = {4}  # session formats this reader understands; anything else is refused
MAX_CHARS = 4096
PROJECT_ID = "DSH"

# USD per million tokens, off-peak: (cache hit, cache miss, output). Peak is double.
# api-docs.deepseek.com/quick_start/pricing, read 2026-11-14. Update with the date.
PRICES: dict[str, tuple[float, float, float]] = {
    "deepseek-v4-pro": (0.022, 0.66, 1.98),
    "deepseek-flash": (0.003, 0.15, 0.60),
}
ALIASES = {"deepseek-v4-flash": "deepseek-flash", "deepseek-v4-flash-vision-exp": "deepseek-flash"}
PEAK_HOURS_UTC = {1, 2, 3, 6, 7, 8, 9}  # Monday to Friday

SECRET_SHAPES = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"),
    re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}"),
]
# NAME=value where NAME looks like a credential: keep the name, drop the value.
SECRET_ASSIGN = re.compile(
    r"(?i)\b([A-Z0-9_]*(?:KEY|SECRET|TOKEN|PASSWORD|PASSWD)[A-Z0-9_]*)(\s*[=:]\s*)['\"]?[^\s'\"]{6,}"
)
URL_PASSWORD = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://[^\s:@/]+:)[^\s@/]+@")
CREDENTIAL_FILE = re.compile(
    r"(?i)(?:^|[\s/\"'=:(])(?:\.env(?:\.[\w.-]+)?|[\w.-]+\.pem|[\w.-]*credentials[\w.-]*"
    r"|id_(?:rsa|ed25519|ecdsa)\w*)(?=$|[\s\"',;:)])"
)


class UnsupportedFormat(ValueError):
    pass


# ---- redaction ------------------------------------------------------------------


def secret_values(paths: Iterable[Path]) -> list[str]:
    """Values (8+ chars) of every KEY=VALUE line in these env files. Never printed."""
    out: set[str] = set()
    for p in paths:
        if not p.is_file():
            continue
        for line in p.read_text(errors="replace").splitlines():
            line = line.strip().removeprefix("export ").strip()
            if line.startswith("#") or "=" not in line:
                continue
            value = line.split("=", 1)[1].strip().strip("'\"")
            if len(value) >= 8:
                out.add(value)
    return sorted(out, key=len, reverse=True)


@dataclass
class Redactor:
    secrets: list[str] = field(default_factory=list)
    max_chars: int = MAX_CHARS

    def __call__(self, text: str) -> str:
        for s in self.secrets:
            text = text.replace(s, "[redacted]")
        for pat in SECRET_SHAPES:
            text = pat.sub("[redacted]", text)
        text = SECRET_ASSIGN.sub(r"\1\2[redacted]", text)
        text = URL_PASSWORD.sub(r"\1[redacted]@", text)
        if len(text) > self.max_chars:
            text = text[: self.max_chars] + f"… [cut {len(text) - self.max_chars} chars]"
        return text


def names_credential_file(arguments: str) -> bool:
    return bool(CREDENTIAL_FILE.search(arguments))


# ---- cost -----------------------------------------------------------------------


@dataclass
class Usage:
    uncached: int = 0
    cache_read: int = 0
    cache_write: int = 0
    output: int = 0

    def add(self, other: Usage) -> None:
        self.uncached += other.uncached
        self.cache_read += other.cache_read
        self.cache_write += other.cache_write
        self.output += other.output

    @classmethod
    def from_event(cls, raw: object) -> Usage:
        u = raw if isinstance(raw, dict) else {}
        return cls(
            uncached=int(u.get("inputTokens") or 0),
            cache_read=int(u.get("cacheReadTokens") or 0),
            cache_write=int(u.get("cacheWriteTokens") or 0),
            output=int(u.get("outputTokens") or 0),
        )


def is_peak(ms: int) -> bool:
    t = datetime.fromtimestamp(ms / 1000, tz=UTC)
    return t.weekday() < 5 and t.hour in PEAK_HOURS_UTC


def cost_usd(model: str, usage: Usage, ms: int) -> float | None:
    """Estimated cost of one model call; None for a model missing from the price table."""
    price = PRICES.get(ALIASES.get(model, model))
    if price is None:
        return None
    hit, miss, out = price
    usd = (usage.cache_read * hit + usage.uncached * miss + usage.output * out) / 1_000_000
    return usd * (2 if is_peak(ms) else 1)


# ---- reading a session ------------------------------------------------------------


@dataclass
class Span:
    name: str
    kind: str  # LLM | TOOL
    start_ms: int
    end_ms: int
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    attributes: dict[str, Any]
    error: bool = False


@dataclass
class Turn:
    number: int
    start_ms: int
    end_ms: int
    end_seq: int
    status: str
    message: str
    reply: str
    spans: list[Span]
    usage: Usage
    cost_usd: float


@dataclass
class Session:
    id: str
    workspace: str
    created_ms: int
    last_ms: int
    title: str
    permission: str
    models: list[str]
    turns: list[Turn]  # finished turns only
    usage: Usage
    cost_usd: float
    unpriced_calls: int
    steps: int
    tool_calls: int
    tool_errors: int
    llm_ms: int
    tool_ms: int


def _text(content: object, kinds: tuple[str, ...] = ("text",)) -> str:
    parts = content if isinstance(content, list) else []
    return "\n".join(
        str(p.get("text", "")) for p in parts if isinstance(p, dict) and p.get("type") in kinds
    )


def _events(path: Path) -> Iterator[dict[str, Any]]:
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def workspace_of(cwd: str, portfolio: Path = PORTFOLIO) -> str | None:
    """The repo a session ran in, or None when it ran outside the portfolio."""
    try:
        rel = Path(cwd).resolve().relative_to(portfolio.resolve())
    except ValueError:
        return None
    return rel.parts[0] if rel.parts else None


def read_session(path: Path, redact: Redactor, workspace: str | None = None) -> Session | None:
    """Parse one session.v4.jsonl; None if it ran outside the portfolio (header read only)."""
    events = _events(path)
    head = next(events, None)
    if not head or head.get("type") != "session":
        raise UnsupportedFormat(f"{path}: no session header")
    if head.get("version") not in FORMATS:
        raise UnsupportedFormat(
            f"{path}: session format v{head.get('version')}, this reader knows {sorted(FORMATS)}"
        )
    ws = workspace or workspace_of(str(head.get("cwd", "")))
    if ws is None:
        return None

    s = Session(
        id=str(head["id"]),
        workspace=ws,
        created_ms=int(head.get("createdAt", 0)),
        last_ms=0,
        title="",
        permission="",
        models=[],
        turns=[],
        usage=Usage(),
        cost_usd=0.0,
        unpriced_calls=0,
        steps=0,
        tool_calls=0,
        tool_errors=0,
        llm_ms=0,
        tool_ms=0,
    )
    turn: dict[str, Any] | None = None
    step_start = 0
    calls: dict[str, tuple[int, str, str]] = {}  # callId -> (time, name, raw arguments)
    for ev in events:
        kind, t, data = ev.get("type"), int(ev.get("time", 0)), ev.get("data") or {}
        s.last_ms = max(s.last_ms, t)
        if kind == "session/title":
            s.title = str(data.get("title", s.title))
        elif kind == "permission/preset":
            s.permission = str(data.get("preset", ""))
        elif kind == "turn/start":
            turn = {
                "n": int(data.get("turn", 0)),
                "start": t,
                "msgs": [],
                "reply": "",
                "spans": [],
                "usage": Usage(),
                "cost": 0.0,
            }
        elif turn is None:
            continue
        elif kind == "user/message" and (data.get("source") or {}).get("kind") == "user":
            turn["msgs"].append(_text(data.get("content")))
        elif kind == "step/start":
            step_start = t
        elif kind == "step/end":
            s.steps += 1
        elif kind in ("assistant/message", "assistant/attempt"):
            msg = data.get("message") or {}
            model = str((msg.get("source") or {}).get("model", ""))
            if model and model not in s.models:
                s.models.append(model)
            usage = Usage.from_event(data.get("usage"))
            usd = cost_usd(model, usage, t) if data.get("usage") else 0.0
            if usd is None:
                s.unpriced_calls += 1
                usd = 0.0
            turn["usage"].add(usage)
            turn["cost"] += usd
            content = msg.get("content")
            reply = _text(content)
            tools = [
                str(p.get("name"))
                for p in content or []
                if isinstance(p, dict) and p.get("type") == "tool-call"
            ]
            failed = kind == "assistant/attempt"
            if reply:
                turn["reply"] = reply
            turn["spans"].append(
                Span(
                    name=f"{model or 'model'} · step {data.get('step', '?')}",
                    kind="LLM",
                    start_ms=step_start or t,
                    end_ms=t,
                    error=failed,
                    inputs={"model": model, "step": data.get("step")},
                    outputs={"text": redact(reply), "tool_calls": tools}
                    if not failed
                    else {"error": "attempt failed"},
                    attributes={
                        "uncached_tokens": usage.uncached,
                        "cache_read_tokens": usage.cache_read,
                        "output_tokens": usage.output,
                        "cost_usd_est": round(usd, 6),
                    },
                )
            )
            s.llm_ms += max(0, t - (step_start or t))
        elif kind == "tool/call":
            calls[str(data.get("callId"))] = (
                t,
                str(data.get("name", "tool")),
                str(data.get("arguments", "")),
            )
            s.tool_calls += 1
        elif kind == "tool/result":
            msg = data.get("message") or {}
            started, name, args = calls.pop(str(msg.get("toolCallId")), (t, "tool", ""))
            is_error = bool(msg.get("isError"))
            s.tool_errors += is_error
            s.tool_ms += max(0, t - started)
            withheld = names_credential_file(args)
            result = (
                "[withheld: the call names a credential file]"
                if withheld
                else redact(_text(msg.get("content")))
            )
            turn["spans"].append(
                Span(
                    name=name,
                    kind="TOOL",
                    start_ms=started,
                    end_ms=t,
                    error=is_error,
                    inputs={"arguments": redact(args)},
                    outputs={"result": result},
                    attributes={"withheld": withheld},
                )
            )
        elif kind == "turn/end":
            reason = data.get("reason") or {}
            s.turns.append(
                Turn(
                    number=turn["n"],
                    start_ms=turn["start"],
                    end_ms=t,
                    end_seq=int(ev.get("seq", -1)),
                    status=str(reason.get("kind", "unknown")),
                    message=redact("\n\n".join(m for m in turn["msgs"] if m)),
                    reply=redact(turn["reply"]),
                    spans=turn["spans"],
                    usage=turn["usage"],
                    cost_usd=turn["cost"],
                )
            )
            s.usage.add(turn["usage"])
            s.cost_usd += turn["cost"]
            turn = None
    s.title = redact(s.title or s.id)[:200]
    return s


def shifted(s: Session, delta_ms: int, suffix: str) -> Session:
    """The same session moved in time and renamed: the smoke replays the fixture as new."""

    def span(sp: Span) -> Span:
        return replace(sp, start_ms=sp.start_ms + delta_ms, end_ms=sp.end_ms + delta_ms)

    turns = [
        replace(
            t,
            start_ms=t.start_ms + delta_ms,
            end_ms=t.end_ms + delta_ms,
            spans=[span(x) for x in t.spans],
        )
        for t in s.turns
    ]
    return replace(
        s,
        id=s.id + suffix,
        created_ms=s.created_ms + delta_ms,
        last_ms=s.last_ms + delta_ms,
        turns=turns,
    )


def find_sessions(root: Path) -> list[Path]:
    return sorted(root.glob("*/*/session.v*.jsonl"))


# ---- writing to MLflow ---------------------------------------------------------------


def git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True
        )
        return out.stdout.strip() or "unknown"
    except OSError:
        return "unknown"


def metrics_of(s: Session) -> dict[str, float]:
    return {
        "turns": len(s.turns),
        "steps": s.steps,
        "tool_calls": s.tool_calls,
        "tool_errors": s.tool_errors,
        "tokens_uncached_input": s.usage.uncached,
        "tokens_cache_read": s.usage.cache_read,
        "tokens_output": s.usage.output,
        "cost_usd_est": round(s.cost_usd, 6),
        "unpriced_calls": s.unpriced_calls,
        "model_seconds": round(s.llm_ms / 1000, 3),
        "tool_seconds": round(s.tool_ms / 1000, 3),
        "wall_seconds": round(max(0, s.last_ms - s.created_ms) / 1000, 3),
    }


def log_session(client: Any, exp_id: str, s: Session, *, smoke: bool = False) -> int:
    """Write the turns not logged yet; return how many traces were written."""
    from mlflow.entities import Metric, RunTag, SpanType

    found = client.search_runs(
        [exp_id], filter_string=f"tags.`dsh.session_id` = '{s.id}'", max_results=1
    )
    run = found[0] if found else None
    through = int(run.data.tags.get("dsh.through_seq", -1)) if run else -1
    new = [t for t in s.turns if t.end_seq > through]
    if run and not new:
        return 0
    if run is None:
        run = client.create_run(
            exp_id,
            start_time=s.created_ms,
            run_name=s.title[:80],
            tags={
                "project": "dsh",
                "git_sha": git_sha(),
                "env": "local",
                "billing": "deepseek-api",
                "dsh.session_id": s.id,
                "workspace": s.workspace,
                "dsh.format": "4",
                **({"dsh.smoke": "true"} if smoke else {}),
            },
        )
    run_id = run.info.run_id
    tags = {"workspace": s.workspace, "dsh.session_id": s.id}
    for t in new:
        ns = 1_000_000
        root = client.start_trace(
            name=f"turn {t.number}",
            span_type=SpanType.AGENT,
            inputs={"message": t.message},
            tags=tags | {"dsh.turn": str(t.number)},
            experiment_id=exp_id,
            start_time_ns=t.start_ms * ns,
            run_id=run_id,
            attributes={
                "status": t.status,
                "cost_usd_est": round(t.cost_usd, 6),
                "tokens_output": t.usage.output,
                "tokens_uncached_input": t.usage.uncached,
                "tokens_cache_read": t.usage.cache_read,
            },
        )
        for sp in t.spans:
            child = client.start_span(
                name=sp.name,
                trace_id=root.trace_id,
                parent_id=root.span_id,
                span_type=SpanType.CHAT_MODEL if sp.kind == "LLM" else SpanType.TOOL,
                inputs=sp.inputs,
                attributes=sp.attributes,
                start_time_ns=sp.start_ms * ns,
            )
            client.end_span(
                root.trace_id,
                child.span_id,
                outputs=sp.outputs,
                status="ERROR" if sp.error else "OK",
                end_time_ns=max(sp.end_ms, sp.start_ms) * ns,
            )
        client.end_trace(
            root.trace_id,
            outputs={"reply": t.reply},
            status="OK" if t.status == "completed" else "ERROR",
            end_time_ns=t.end_ms * ns,
        )
    ts = s.last_ms
    client.log_batch(
        run_id,
        metrics=[Metric(k, float(v), ts, len(s.turns)) for k, v in metrics_of(s).items()],
        tags=[
            RunTag("dsh.through_seq", str(max(t.end_seq for t in s.turns))),
            RunTag("mlflow.runName", s.title[:80]),
            RunTag("dsh.models", ",".join(s.models) or "none"),
            RunTag("dsh.permission", s.permission or "unknown"),
        ],
    )
    client.set_terminated(run_id, "FINISHED", end_time=s.last_ms)
    return len(new)


# ---- command -------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument(
        "--sessions", type=Path, default=None, help="default: $DSH_HOME/sessions or ~/.dsh/sessions"
    )
    ap.add_argument(
        "--fixture", type=Path, default=None, help="replay these sessions as new (the smoke)"
    )
    ap.add_argument(
        "--dry-run", action="store_true", help="print what would be logged; write nothing"
    )
    ap.add_argument("--uri", default=None)
    args = ap.parse_args()

    if args.fixture:
        root = args.fixture
    else:
        home = os.environ.get("DSH_HOME", "").strip()
        root = (
            args.sessions
            or (Path(home).expanduser() if home else Path.home() / ".dsh") / "sessions"
        )
    redact = Redactor(secret_values([Path.home() / ".env", ROOT / ".env"]))

    sessions: list[Session] = []
    bad = skipped = 0
    for path in find_sessions(root):
        try:
            s = read_session(path, redact, workspace="fixture" if args.fixture else None)
        except (UnsupportedFormat, json.JSONDecodeError, KeyError) as e:
            print(f"  FAIL {e}", file=sys.stderr)
            bad += 1
            continue
        if s is None:
            skipped += 1
            continue
        if args.fixture:
            s = shifted(s, int(time.time() * 1000) - s.created_ms, f"-smoke-{uuid.uuid4().hex[:8]}")
        if s.turns:
            sessions.append(s)
    print(
        f"{len(sessions)} session(s) with finished turns; {skipped} outside the portfolio, not read"
    )

    if args.dry_run:
        for s in sessions:
            m = metrics_of(s)
            cost = f"cost≈${m['cost_usd_est']:.4f}"
            print(f"  {s.workspace:<18} {s.id}  turns={len(s.turns)} {cost}  {s.title[:50]}")
        return 1 if bad else 0

    import mlflow
    from mlflow import MlflowClient

    reg = load_registry()
    uri = resolve_uri(args.uri, reg)
    mlflow.set_tracking_uri(uri)
    client = MlflowClient(tracking_uri=uri)
    name = reg.by_id(PROJECT_ID).experiments[0]
    try:
        exp = client.get_experiment_by_name(name)
    except Exception as e:
        print(f"MLflow unreachable at {uri}: {e}", file=sys.stderr)
        return 2
    if exp is None:
        print(f"experiment {name} is missing: run `make mlflow-init`", file=sys.stderr)
        return 2
    written = 0
    for s in sessions:
        n = log_session(client, exp.experiment_id, s, smoke=bool(args.fixture))
        if n:
            print(f"  {s.workspace:<18} {s.id}  +{n} turn(s)  cost≈${s.cost_usd:.4f}")
        written += n
    mlflow.flush_trace_async_logging()
    print(f"logged {written} new turn(s) to {name} at {uri}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
