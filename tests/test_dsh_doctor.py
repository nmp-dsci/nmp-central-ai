"""The dsh launcher refuses to start while any upload to DeepSeek is on (D39)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from dsh_doctor import (  # noqa: E402
    PASS_THROUGH,
    clean_env,
    in_portfolio,
    install_plan,
    node_ok,
    parse_dump,
    upload_findings,
)

LOCKED = """
- id: session-log-deepseek
  name: '@deepseek-ai/dsh-session-log-deepseek'
  config: {enabled: false, maxBytes: 8388608}
- id: session-telemetry-otel
  name: '@deepseek-ai/dsh-session-telemetry-otel'
  config: {mode: DISABLED}
- id: plugin-package-inventory-deepseek
  name: '@deepseek-ai/dsh-plugin-package-inventory-deepseek'
  config: {enabled: false}
- id: timer
  name: '@deepseek-ai/cordis-plugin-timer'
"""


def test_the_home_patch_state_passes() -> None:
    assert upload_findings(parse_dump(LOCKED)) == []


def test_shipped_defaults_fail() -> None:
    shipped = """
- id: session-log-deepseek
  name: '@deepseek-ai/dsh-session-log-deepseek'
- id: session-telemetry-otel
  name: '@deepseek-ai/dsh-session-telemetry-otel'
  config:
    mode: !!js process.env.DSH_TELEMETRY_MODE || 'FEEDBACK_ONLY'
- id: plugin-package-inventory-deepseek
  name: '@deepseek-ai/dsh-plugin-package-inventory-deepseek'
"""
    found = upload_findings(parse_dump(shipped))
    assert len(found) == 3  # an unevaluated !!js expression proves nothing, so it fails too


def test_a_renamed_row_is_still_caught_by_package_name() -> None:
    renamed = LOCKED.replace("id: session-log-deepseek", "id: session-log-v2").replace(
        "{enabled: false, maxBytes: 8388608}", "{enabled: true}"
    )
    assert len(upload_findings(parse_dump(renamed))) == 1


def test_a_disabled_row_uploads_nothing() -> None:
    rows = parse_dump(
        "- id: x\n  name: '@deepseek-ai/dsh-session-log-deepseek'\n  disabled: true\n"
    )
    assert upload_findings(rows) == []


def test_the_launch_environment_carries_no_keys() -> None:
    env = clean_env({"HOME": "/h", "PATH": "/bin", "DEEPSEEK_API_KEY": "k", "AWS_PROFILE": "p"})
    assert "DEEPSEEK_API_KEY" not in env and "AWS_PROFILE" not in env
    assert set(env) - set(PASS_THROUGH) == {
        "DSH_TELEMETRY_MODE",
        "DSH_TELEMETRY_DISABLED",
        "DSH_TUI_UPDATE_ENGINE",
        "DSH_TUI_UPDATE_LAUNCHER",
    }
    assert env["DSH_TELEMETRY_MODE"] == "DISABLED"


def test_only_portfolio_directories_launch(tmp_path: Path) -> None:
    assert in_portfolio(tmp_path / "repo", portfolio=tmp_path)
    assert not in_portfolio(Path("/tmp"), portfolio=tmp_path / "portfolio")


def test_node_floor() -> None:
    assert node_ok("v25.8.1") and node_ok("v24.9.0")
    assert not node_ok("v24.8.0") and not node_ok("v22.19.0") and not node_ok("missing")


def test_install_refuses_an_edited_copy(tmp_path: Path) -> None:
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.mkdir()
    dst.mkdir()
    for name in ("home.cordis.patch.yml", "AGENTS.md"):
        (src / name).write_text(name)
    assert {a for _, _, a in install_plan(src, dst, force=False)} == {"copy"}
    (dst / "cordis.patch.yml").write_text("edited")
    (dst / "AGENTS.md").write_text("AGENTS.md")
    actions = {d.name: a for _, d, a in install_plan(src, dst, force=False)}
    assert actions == {"cordis.patch.yml": "refuse", "AGENTS.md": "same"}
    assert {d.name: a for _, d, a in install_plan(src, dst, force=True)}[
        "cordis.patch.yml"
    ] == "copy"
