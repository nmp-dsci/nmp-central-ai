#!/usr/bin/env python
"""Audit that every repo under the portfolio is coding-agent agnostic.

The standard: `AGENTS.md` is the single source of truth, skills live in
`.agents/skills/<name>/SKILL.md`, and `CLAUDE.md` / `.claude/skills` are thin shims that only
point at them. Non-zero exit on any miss.

    uv run scripts/agent_check.py [--root ~/git/nmp-ai-portfolio]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

CODEX_DEFAULT_LIMIT = 32 * 1024


def check_repo(repo: Path) -> list[str]:
    errs: list[str] = []
    agents = repo / "AGENTS.md"
    if not agents.is_file() or agents.is_symlink():
        errs.append("AGENTS.md missing or a symlink (it must be the real file)")
    elif not agents.read_text().strip():
        errs.append("AGENTS.md is empty")
    claude = repo / "CLAUDE.md"
    if claude.exists() and (claude.is_symlink() or claude.read_text().strip() != "@AGENTS.md"):
        errs.append("CLAUDE.md must be exactly '@AGENTS.md' (guidance belongs in AGENTS.md)")
    for stray in (".claude/commands", ".codex/skills", "skills"):
        if (repo / stray).exists():
            errs.append(f"{stray}/ should not exist (use .agents/skills/)")
    shim = repo / ".claude" / "skills"
    if shim.exists() or shim.is_symlink():
        if not shim.is_symlink() or shim.readlink().as_posix() != "../.agents/skills":
            errs.append(".claude/skills must be a symlink to ../.agents/skills")
    skills = repo / ".agents" / "skills"
    if skills.is_dir():
        for d in sorted(p for p in skills.iterdir() if p.is_dir()):
            f = d / "SKILL.md"
            if not f.is_file():
                errs.append(f"{d.name}: no SKILL.md")
                continue
            head = f.read_text().split("---")[1] if f.read_text().startswith("---") else ""
            if not re.search(rf"^name:\s*{re.escape(d.name)}\s*$", head, re.M):
                errs.append(f"{d.name}: SKILL.md frontmatter name must equal the directory name")
            if not re.search(r"^description:", head, re.M):
                errs.append(f"{d.name}: SKILL.md has no description")
    elif shim.exists():
        errs.append(".claude/skills points at a missing .agents/skills")
    if agents.is_file():
        size = agents.stat().st_size
        if size > CODEX_DEFAULT_LIMIT:
            cfg = repo / ".codex" / "config.toml"
            m = (
                re.search(r"project_doc_max_bytes\s*=\s*(\d+)", cfg.read_text())
                if cfg.is_file()
                else None
            )
            if not m or int(m.group(1)) < size:
                errs.append(f"AGENTS.md is {size} B (>32 KiB): set project_doc_max_bytes")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    root = ap.parse_args().root
    # A `.git` file marks a linked worktree, which shares its main repo's setup: skip it.
    repos = sorted(p for p in root.iterdir() if (p / ".git").is_dir())
    bad = 0
    for r in repos:
        errs = check_repo(r)
        bad += bool(errs)
        print(f"{'FAIL' if errs else 'ok  '}  {r.name}")
        for e in errs:
            print(f"        - {e}")
    top = root / "AGENTS.md"
    if not top.is_file() or (root / "CLAUDE.md").read_text().strip() != "@AGENTS.md":
        print("FAIL  portfolio level: run `make install-agent-context`")
        bad += 1
    print(f"\n{len(repos)} repos, {bad} failing")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
