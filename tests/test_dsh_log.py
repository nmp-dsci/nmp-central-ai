"""dsh sessions reach MLflow as a run each and a trace per finished turn, never with secrets."""

from __future__ import annotations

import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import dsh_log  # noqa: E402
from dsh_log import (  # noqa: E402
    Redactor,
    UnsupportedFormat,
    Usage,
    cost_usd,
    find_sessions,
    log_session,
    read_session,
    secret_values,
    workspace_of,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "dsh"
FAKES = [
    "sk-fixturefakefakefakefake0000",
    "AKIAFIXTUREFAKE00000",
    "hunter2-fixture",
    "abcdef123456",
]


def session() -> dsh_log.Session:
    s = read_session(find_sessions(FIXTURE)[0], Redactor(), workspace="fixture")
    assert s is not None
    return s


def everything_logged(s: dsh_log.Session) -> str:
    """Every string that would leave this machine for MLflow."""
    parts: list[Any] = [s.title]
    for t in s.turns:
        parts += [t.message, t.reply] + [[sp.name, sp.inputs, sp.outputs] for sp in t.spans]
    return json.dumps(parts)


def test_only_finished_turns_are_read() -> None:
    s = session()
    assert [t.number for t in s.turns] == [1, 2]  # turn 3 is still running
    assert [t.status for t in s.turns] == ["completed", "completed"]


def test_usage_and_tool_calls_come_from_the_log() -> None:
    s = session()
    assert s.tool_calls == 2 and s.tool_errors == 0
    assert s.steps == 4
    assert s.usage.output == 57 + 100 + 40 + 40
    assert s.usage.cache_read == 6528 + 6000 + 6000
    kinds = [sp.kind for sp in s.turns[0].spans]
    assert kinds == ["LLM", "TOOL", "LLM"]
    assert s.turns[0].reply == "1"
    assert s.models == ["deepseek-flash", "deepseek-v4-pro"]


def test_no_planted_secret_or_reasoning_reaches_mlflow() -> None:
    logged = everything_logged(session())
    for fake in FAKES:
        assert fake not in logged
    assert "PRIVATE REASONING" not in logged
    assert "[redacted]" in logged


def test_a_credential_file_read_is_withheld_whole() -> None:
    tool = [sp for sp in session().turns[1].spans if sp.kind == "TOOL"][0]
    assert tool.outputs["result"].startswith("[withheld")
    assert "OPENAI_API_KEY" not in json.dumps(tool.outputs)


def test_env_file_values_are_redacted(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("export MY_SERVICE_PASS='correct-horse-battery'\nSHORT=abc\n# comment\n")
    r = Redactor(secret_values([env]))
    assert r("login with correct-horse-battery please") == "login with [redacted] please"
    assert "abc" in r("abc")  # values under 8 chars are not treated as secrets


def test_long_text_is_cut() -> None:
    out = Redactor(max_chars=10)("x" * 50)
    assert out.startswith("x" * 10) and "cut 40 chars" in out


def test_sessions_outside_the_portfolio_are_not_read(tmp_path: Path) -> None:
    assert workspace_of("/tmp/elsewhere", portfolio=tmp_path) is None
    assert workspace_of(str(tmp_path / "repo" / "sub"), portfolio=tmp_path) == "repo"
    path = find_sessions(FIXTURE)[0]
    assert read_session(path, Redactor()) is None  # its cwd is a placeholder outside the portfolio


def test_unknown_session_format_is_refused(tmp_path: Path) -> None:
    d = tmp_path / "--x--" / "session-1"
    d.mkdir(parents=True)
    f = d / "session.v5.jsonl"
    f.write_text(json.dumps({"type": "session", "version": 5, "id": "s", "cwd": "/"}) + "\n")
    with pytest.raises(UnsupportedFormat):
        read_session(f, Redactor(), workspace="x")


def test_peak_hours_double_the_price() -> None:
    usage = Usage(uncached=1_000_000)
    off = int(datetime(2026, 11, 14, 12, tzinfo=UTC).timestamp() * 1000)  # Saturday
    peak = int(datetime(2026, 11, 16, 2, tzinfo=UTC).timestamp() * 1000)  # Monday 02:00 UTC
    assert cost_usd("deepseek-v4-pro", usage, off) == pytest.approx(0.66)
    assert cost_usd("deepseek-v4-pro", usage, peak) == pytest.approx(1.32)
    assert cost_usd("deepseek-v4-flash", usage, off) == pytest.approx(0.15)  # legacy alias
    assert cost_usd("someone-else", usage, off) is None


class FakeClient:
    """Records what log_session sends; behaves like MlflowClient for the calls it makes."""

    def __init__(self) -> None:
        self.runs: dict[str, SimpleNamespace] = {}
        self.traces: list[dict[str, Any]] = []
        self.spans: list[dict[str, Any]] = []

    def search_runs(self, exp_ids: list[str], filter_string: str, max_results: int) -> list[Any]:
        return [
            r for r in self.runs.values() if f"'{r.data.tags['dsh.session_id']}'" in filter_string
        ]

    def create_run(self, exp_id: str, start_time: int, run_name: str, tags: dict[str, str]) -> Any:
        run = SimpleNamespace(
            info=SimpleNamespace(run_id=f"r{len(self.runs)}"), data=SimpleNamespace(tags=dict(tags))
        )
        self.runs[run.info.run_id] = run
        return run

    def start_trace(self, **kw: Any) -> Any:
        self.traces.append(kw)
        return SimpleNamespace(trace_id=f"t{len(self.traces)}", span_id="root")

    def start_span(self, **kw: Any) -> Any:
        self.spans.append(kw)
        return SimpleNamespace(span_id=f"s{len(self.spans)}")

    def end_span(self, *a: Any, **kw: Any) -> None: ...

    def end_trace(self, *a: Any, **kw: Any) -> None: ...

    def set_terminated(self, *a: Any, **kw: Any) -> None: ...

    def log_batch(self, run_id: str, metrics: list[Any], tags: list[Any]) -> None:
        self.runs[run_id].data.tags.update({t.key: t.value for t in tags})


def test_a_rerun_logs_only_new_turns(tmp_path: Path) -> None:
    pytest.importorskip("mlflow")
    client = FakeClient()
    s = session()
    assert log_session(client, "1", s) == 2
    assert log_session(client, "1", s) == 0  # nothing new: no duplicate traces
    assert len(client.runs) == 1 and len(client.traces) == 2
    assert {t["run_id"] for t in client.traces} == {"r0"}
    run_tags = client.runs["r0"].data.tags
    for required in ("project", "git_sha", "env", "billing"):
        assert required in run_tags  # PLATFORM.md: required run tags

    # the session grows by one finished turn: only that turn is logged
    src = find_sessions(FIXTURE)[0]
    grown = tmp_path / src.parent.parent.name / src.parent.name
    grown.mkdir(parents=True)
    lines = src.read_text().splitlines()
    last = json.loads(lines[-1])
    lines.append(json.dumps({"type": "turn/end", "seq": last["seq"] + 1, "time": last["time"] + 5,
                             "data": {"turn": 3, "reason": {"kind": "cancelled"}}}))  # fmt: skip
    (grown / src.name).write_text("\n".join(lines) + "\n")
    s2 = read_session(grown / src.name, Redactor(), workspace="fixture")
    assert s2 is not None
    assert log_session(client, "1", s2) == 1
    assert client.traces[-1]["name"] == "turn 3"
    shutil.rmtree(tmp_path / src.parent.parent.name)
