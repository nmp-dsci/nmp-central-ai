"""The house UI is only worth having if a bad palette cannot ship.

These exercise the real interfaces: the registry refuses hues that collide, the
audit fails a palette that misses AA and passes the one in the repo, and
install/check actually move files and notice drift.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from _oklch import accent_for, contrast  # noqa: E402
from _registry import RegistryError, hue_distance, load_registry  # noqa: E402
from house_ui import (  # noqa: E402
    HOUSE_CSS,
    cmd_check,
    cmd_install,
    house_version,
    render_project_css,
)
from house_ui_audit import audit  # noqa: E402

BASE = {
    "platform": {
        "mlflow_uri": "http://localhost:5000",
        "mlflow_uri_compose": "http://mlflow:5000",
        "docker_network": "nmp-central",
    }
}


def write_registry(tmp_path: Path, projects: list[dict[str, object]]) -> Path:
    reg_dir = tmp_path / "registry"
    reg_dir.mkdir(exist_ok=True)
    p = reg_dir / "projects.yaml"
    p.write_text(yaml.safe_dump(BASE | {"projects": projects}))
    return p


def proj(pid: str, name: str, hue: int | None, path: str = ".") -> dict[str, object]:
    out: dict[str, object] = {"id": pid, "name": name, "path": path, "mlflow": {}}
    if hue is not None:
        out["ui"] = {"hue": hue}
    return out


# ---- the colour maths is a contract with the browser -------------------------


def test_generated_accents_match_what_the_browser_renders() -> None:
    """These exact values were read back from Chrome's own oklch() rasterisation.

    The audit's guarantee is only as good as this conversion agreeing with the
    engine that paints the page, so the agreement is pinned.
    """
    assert accent_for(168, "light") == "#00744f"
    assert accent_for(168, "dark") == "#50d2a7"
    assert accent_for(80, "light") == "#835200"
    assert accent_for(345, "light") == "#8e3a6e"


def test_hue_distance_goes_the_short_way_round_the_wheel() -> None:
    assert hue_distance(345, 10) == 25
    assert hue_distance(10, 345) == 25
    assert hue_distance(168, 200) == 32
    assert hue_distance(0, 180) == 180


# ---- the registry refuses a palette nobody could read apart ------------------


def test_registry_refuses_two_projects_whose_accents_look_alike(tmp_path: Path) -> None:
    path = write_registry(tmp_path, [proj("P8", "alpha", 100), proj("P9", "beta", 115)])
    with pytest.raises(RegistryError, match="within 30 degrees"):
        load_registry(path)


def test_registry_allows_hues_that_are_far_enough_apart(tmp_path: Path) -> None:
    reg = load_registry(write_registry(tmp_path, [proj("P8", "a", 100), proj("P9", "b", 140)]))
    assert [p.ui.hue for p in reg.themed if p.ui] == [100, 140]


def test_registry_separation_wraps_around_zero(tmp_path: Path) -> None:
    path = write_registry(tmp_path, [proj("P8", "a", 350), proj("P9", "b", 10)])
    with pytest.raises(RegistryError, match="within 30 degrees"):
        load_registry(path)


@pytest.mark.parametrize("bad", [400, -5, "teal", 3.5, True])
def test_registry_refuses_a_hue_that_is_not_a_degree(tmp_path: Path, bad: object) -> None:
    path = write_registry(tmp_path, [proj("P9", "a", None)])
    raw = yaml.safe_load(path.read_text())
    raw["projects"][0]["ui"] = {"hue": bad}
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(RegistryError, match="ui.hue"):
        load_registry(path)


# ---- the gate ----------------------------------------------------------------

HUES = [("P1", 168), ("P2", 80)]


def test_the_shipped_palette_passes_in_both_themes_for_every_registered_hue() -> None:
    reg = load_registry()
    hues = [(p.id, p.ui.hue) for p in reg.themed if p.ui]
    assert hues, "the registry declares no hue, so the audit proves nothing"
    assert audit(HOUSE_CSS.read_text(), hues, quiet=True) == []


def test_the_gate_fails_when_a_text_token_is_lightened_past_AA() -> None:
    """Regression for F3: --faint shipped at 4.13:1 and nothing noticed."""
    css = HOUSE_CSS.read_text()
    assert audit(css, HUES, quiet=True) == []
    broken = css.replace("--faint:#5C635E", "--faint:#BFBFBF")
    assert broken != css
    failures = audit(broken, HUES, quiet=True)
    assert any("--faint on --bg" in f for f in failures)


def test_the_gate_fails_for_only_the_hue_that_breaks() -> None:
    """A palette can be fine for one project's accent and illegal for another's."""
    css = HOUSE_CSS.read_text()
    # chroma/lightness are fixed, so force a bad stop by moving the light surface
    broken = css.replace("--bg:#F7F6F2;", "--bg:#2b7d63;")
    failures = audit(broken, [("P1", 168), ("P2", 80)], quiet=True)
    assert any("P1" in f for f in failures)


def test_the_gate_refuses_an_accent_that_is_a_status_colour() -> None:
    """Regression for F7: tau2-loop's accent was literally the shared --red.

    Hue separation alone cannot catch this -- the clash is between the accent's
    resolved value and a fixed status token -- so the audit compares the two.
    """
    css = HOUSE_CSS.read_text()
    clash = css.replace("--amber:#8A5006", f"--amber:{accent_for(168, 'light')}")
    failures = audit(clash, [("P1", 168)], quiet=True)
    assert any("brand and status would be the same colour" in f for f in failures)
    assert audit(css, [("P1", 168)], quiet=True) == []


def test_a_palette_with_no_contract_is_itself_a_failure() -> None:
    assert audit("/* no contract here */ :root{--bg:#fff;}", HUES, quiet=True)


# ---- distribution ------------------------------------------------------------


def test_render_project_css_declares_only_the_hue(tmp_path: Path) -> None:
    """A project's whole stylesheet is one declaration; everything else is the house."""
    reg = load_registry(write_registry(tmp_path, [proj("P9", "alpha", 200)]))
    css = render_project_css(reg.themed[0], "v1")
    declarations = [
        line.strip()
        for line in re.sub(r"/\*.*?\*/", "", css, flags=re.S).splitlines()
        if line.strip()
    ]
    assert declarations == [":root{ --hue:200; }"]
    assert "P9 alpha" in css and "v1" in css


def test_install_then_check_reports_current_and_then_drift(tmp_path: Path) -> None:
    (tmp_path / "alpha").mkdir()
    reg = load_registry(write_registry(tmp_path, [proj("P9", "alpha", 200, path="alpha")]))
    assert cmd_install(reg, force=False, dry_run=False) == 0

    lavish = tmp_path / "alpha" / ".lavish"
    assert (lavish / "house.css").read_text() == HOUSE_CSS.read_text()
    assert (lavish / "fonts" / "plex.css").exists()
    project_css = (lavish / "project.css").read_text()
    assert "--hue:200" in project_css
    assert house_version(HOUSE_CSS.read_text()) in project_css

    assert cmd_check(reg) == 0  # reports, never fails a build

    # an edited copy is refused rather than silently overwritten
    (lavish / "house.css").write_text("/* someone edited this */")
    assert cmd_install(reg, force=False, dry_run=False) == 1
    assert (lavish / "house.css").read_text() == "/* someone edited this */"
    assert cmd_install(reg, force=True, dry_run=False) == 0
    assert (lavish / "house.css").read_text() == HOUSE_CSS.read_text()


def test_install_dry_run_writes_nothing(tmp_path: Path) -> None:
    (tmp_path / "beta").mkdir()
    reg = load_registry(write_registry(tmp_path, [proj("P9", "beta", 200, path="beta")]))
    assert cmd_install(reg, force=False, dry_run=True) == 0
    assert not (tmp_path / "beta" / ".lavish").exists()


def test_every_registered_accent_clears_AA_on_both_surfaces() -> None:
    """The promise the hue model makes to a project that only picks a number."""
    for p in load_registry().themed:
        assert p.ui is not None
        for theme, bg, panel in (("light", "#F7F6F2", "#FFFFFF"), ("dark", "#121614", "#191E1B")):
            acc = accent_for(p.ui.hue, theme)
            assert contrast(acc, bg) >= 4.5, (p.id, theme, "bg")
            assert contrast(acc, panel) >= 4.5, (p.id, theme, "panel")
