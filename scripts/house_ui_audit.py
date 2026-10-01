#!/usr/bin/env python3
"""house_ui_audit.py — fail the build when the house UI misses WCAG AA.

The tokens live in one file (agent/house/house.css). Every pair that has to be
legible is declared there in `@contrast` comment lines:

    @contrast --faint --bg 4.5 | --accent --panel 4.5 | --line-3 --bg 3.0

This resolves each token in BOTH themes -- the `:root` block (light, the reference
palette) and `:root[data-theme="dark"]`, which inherits anything it does not
redefine -- and then, because the accent is generated from a per-project hue
(D28), re-checks every accent-bearing pair once per hue declared in
registry/projects.yaml. A palette that is fine for the platform's green but
illegible for a project's violet is a bug this catches before anyone sees it.

It also refuses an accent that resolves to one of the fixed status colours: that
is finding F7, where tau2-loop's accent was literally the shared `--red`.

    uv run python scripts/house_ui_audit.py
    uv run python scripts/house_ui_audit.py --quiet

No third-party dependency beyond the registry loader, so it runs anywhere.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _oklch import accent_for, accent_soft_for, contrast  # noqa: E402
from _registry import ROOT, load_registry  # noqa: E402

HOUSE_CSS = ROOT / "agent" / "house" / "house.css"
DECL = re.compile(r"(--[\w-]+)\s*:\s*([^;}]+)")
CONTRAST = re.compile(r"@contrast([^*\n]+)")
PAIR = re.compile(r"(--[\w-]+)\s+(--[\w-]+)\s+([0-9.]+)")
HEX = re.compile(r"^#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$")
# tokens the accent is generated into, so they vary per project and per theme
GENERATED = {"--accent", "--accent-soft"}
STATUS = ("--amber", "--red", "--blue")


COMMENT = re.compile(r"/\*.*?\*/", re.S)


def strip_comments(css: str) -> str:
    """Comments are stripped before tokens are read.

    The header documents the seam with a literal `:root{ --hue:80 }` example, and
    a naive search finds that comment before the real block.
    """
    return COMMENT.sub("", css)


def _block(css: str, selector: str) -> dict[str, str]:
    """The literal token declarations inside one selector's first block."""
    i = css.find(selector)
    if i < 0:
        return {}
    start = css.index("{", i)
    depth, j = 0, start
    while j < len(css):
        if css[j] == "{":
            depth += 1
        elif css[j] == "}":
            depth -= 1
            if depth == 0:
                break
        j += 1
    body = css[start : j + 1]
    return {k: v.strip() for k, v in DECL.findall(body) if HEX.match(v.strip())}


def palettes(css: str) -> dict[str, dict[str, str]]:
    """Light is the reference; dark inherits whatever it does not redefine."""
    bare = strip_comments(css)
    light = _block(bare, ":root{")
    dark = dict(light) | _block(bare, ':root[data-theme="dark"]')
    return {"light": light, "dark": dark}


def declared_pairs(css: str) -> list[tuple[str, str, float]]:
    out: list[tuple[str, str, float]] = []
    for line in CONTRAST.findall(css):
        for a, b, ratio in PAIR.findall(line):
            out.append((a, b, float(ratio)))
    return out


def audit(css: str, hues: list[tuple[str, int]], quiet: bool = False) -> list[str]:
    pal = palettes(css)
    pairs = declared_pairs(css)
    if not pairs:
        return [f"{HOUSE_CSS}: no @contrast lines found -- the contract is missing"]
    failures: list[str] = []
    checked = 0
    for theme, base in pal.items():
        for pid, hue in hues:
            tokens = dict(base)
            tokens["--accent"] = accent_for(hue, theme)
            tokens["--accent-soft"] = accent_soft_for(hue, theme)
            for a, b, want in pairs:
                # pairs with no generated token only need checking once per theme
                if not (GENERATED & {a, b}) and pid != hues[0][0]:
                    continue
                if a not in tokens or b not in tokens:
                    failures.append(f"{theme}: @contrast names unknown token {a} or {b}")
                    continue
                got = contrast(tokens[a], tokens[b])
                checked += 1
                if got < want:
                    failures.append(
                        f"{theme} {pid} hue {hue}: {a} on {b} is {got:.2f}:1, needs {want}"
                    )
            for status in STATUS:
                if tokens.get(status) == tokens["--accent"]:
                    failures.append(
                        f"{theme} {pid} hue {hue}: accent resolves to {status} "
                        f"({tokens['--accent']}) -- brand and status would be the same colour"
                    )
    if not quiet:
        print(
            f"house UI: {checked} contrast checks across {len(pal)} themes "
            f"and {len(hues)} hues -- {'FAIL' if failures else 'all pass'}"
        )
    return failures


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("css", nargs="?", type=Path, default=HOUSE_CSS)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    reg = load_registry()
    hues = [(p.id, p.ui.hue) for p in reg.themed if p.ui]
    if not hues:
        print("no project declares ui.hue; nothing to audit", file=sys.stderr)
        return 1
    failures = audit(args.css.read_text(), hues, quiet=args.quiet)
    for f in failures:
        print(f"  FAIL {f}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
