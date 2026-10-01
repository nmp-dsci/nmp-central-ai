# s05 — the house UI (plan of record + build receipt)

Status: decided and **built** 2026-10-01 · Review artifact: `.lavish/s03_house-ui-review.html`
Branch: `house-ui-review` · Decisions: D25–D32 in `AGENTS.md` · Runbook: `docs/runbooks/house-ui.md`

## Goal

One look across the portfolio, one colour per project, one place to change it. The house UI
becomes the third shared asset here, next to MLflow and Postgres, and is built the same way:
the registry is the source of truth, a script renders from it, a `make` target applies it,
`make check` proves it.

## What the review found

Measured across 21 `.lavish/` directories and 277 artifacts:

| Finding | Evidence |
|---|---|
| The house UI already existed and was already running | tau2-loop, DataAgentBench, ConvFinQA-agent and nmp-dsci.github.io share **45 token names**, with light and dark palettes and a different accent each. DataAgentBench: 15/15 artifacts dual-theme, 15/15 with a focus ring. |
| It was never a file | 39,894 lines of inline `<style>` across the portfolio. The only file form was `nmp-dsci.github.io/_o/assets/css/tokens.css`, in the site repo. |
| `nmp-central-ai` was the outlier | dark-only, Geist, 21 tokens — missing 27 of the shared 45. No print styles, no focus ring, no light stop. |
| The accent was not a seam | `td.rec{background:rgba(92,200,166,0.06)}` hardcoded the teal, so swapping `--accent` would not have changed it (F2). |
| `--faint` missed WCAG AA | 4.13:1 on `--bg`, 3.80:1 on `--panel`, on the smallest text on the page (F3). |
| A single accent hex cannot serve both themes | against light paper every dark accent in the portfolio fails: the old house teal `#5cc8a6` scores 1.89:1. |
| One accent *was* a status colour | tau2-loop's `#E08A7A` is the shared `--red` (F7). |
| Print was a portfolio-wide gap | 11 of 277 artifacts have `@media print`, none of them in the four house-system directories. |

## The decisions (D25–D32)

Recommended defaults, all accepted: canon lives here and is installed outward (D25); every
project that declares a hue receives it (D26); IBM Plex self-hosted, Geist retired (D27);
**one `--hue` integer per project with both stops derived by `oklch()`** (D28); vendored copy
plus version stamp and drift check, no symlink and no CDN (D29); the 277 existing artifacts
stay pinned (D30); the contrast audit and drift check run in `make check` and CI (D31); the
house hue 168 stays with the platform and the site (D32).

## Why one hue

Converting every accent already in use to OKLCH showed lightness clustered at 0.72–0.76 and
chroma at 0.10–0.13 — only hue varied. Making that explicit turns contrast into a property of
the system: light stop `oklch(0.48 0.13 H)`, dark stop `oklch(0.78 0.13 H)`.

Worst ratio across the nine registered projects, both themes, every audited pair: **4.91:1**
against a 4.5 threshold; worst accent-on-surface: **5.33:1**. Chrome's own `oklch()`
rasterisation was read back and matches the generated table exactly, so the gate checks the
same numbers the browser paints.

## Receipt — every submitted scope item

| ID | Item | Outcome |
|----|------|---------|
| S1 | Layer 1 tokens | **addressed** — `agent/house/house.css`, the 45-name vocabulary promoted from the site's `tokens.css`, plus `--hue`, `--accent-wash` (fixes F2), the four-step ink ramp (F3), the scales (F4), `@media print` (F1), `:focus-visible` and `accent-color` (F8), `prefers-reduced-motion` and `--measure` (F10). Version-stamped `v1`. |
| S2 | Layer 2 components | **addressed** — the shared artifact vocabulary rebuilt on the tokens, with no literal outside `:root`. Layer 2b aliases all 19 class names tau2-loop, DataAgentBench and ConvFinQA-agent already use (`wrap tw kpi lead chip chips btn label small top dia fig-title grid v-ok sr-only`), so an existing artifact can adopt by swapping its `<style>` for a `<link>` without touching markup. |
| S3 | Registry `ui.hue` | **addressed** — `Ui` dataclass, `_parse_ui`, `hue_distance`, `validate_ui` refusing two projects within 30°; nine hues declared (D32). Separation is enforced project-to-project only, not against status hues — that would remove about half the wheel; the status *value* clash (F7) is caught by the audit instead. |
| S4 | Render + audit + CI | **addressed** — `scripts/_oklch.py` (OKLab↔sRGB, WCAG, no dependency), `scripts/house_ui.py` (`render`/`install`/`check`/`table`), `scripts/house_ui_audit.py` reading the `@contrast` contract over both themes × every hue (130 checks) and refusing an accent that resolves to a status colour. `tests/test_house_ui.py`: 19 tests including fail-before/pass-after for F3 and F7. Two CI steps in the `scripts` job. |
| S5 | Make targets | **addressed** — `house-ui`, `install-house-ui` (cmp-guarded, `FORCE=1`), `house-ui-check`; the audit and the drift report both wired into `make check`. |
| S6 | Self-hosted fonts | **addressed** — five IBM Plex woff2 subsets vendored to `agent/house/fonts/` with `plex.css` rewritten to relative paths (the site's copy uses root-absolute paths and cannot be vendored as-is) and the OFL notice. Fixes F6. |
| S7 | Scaffold + site | **not selected** — left unticked in the scope batch because it edits `ai-project-template` and `nmp-dsci.github.io`. Still the highest-leverage follow-up: a scaffold that ships the link means no future project repeats this. |
| S8 | Docs + skill | **addressed** — `PLATFORM.md` House UI table + rule zero; `AGENTS.md` D25–D32; `CLAUDE.md` quick ref and rule; `README.md`; `docs/runbooks/house-ui.md`; plugin skill `platform-ui`; plugin 0.2.1 → 0.3.0. |

## Verification

`make house-ui` → 130 contrast checks across 2 themes and 9 hues, all pass; worst
accent/surface ratio 5.33:1. `make lint` → ruff + mypy strict clean. `uv run pytest -q` → all
green. `make house-ui-check` → PLATFORM current at v1, the other eight absent until their
fan-out is run.

## Deliberately not done

- **The fan-out was not executed.** `make install-house-ui` writes into eight sibling
  repositories. The target is built and dry-run proven; running it is the user's call, and
  each sibling needs its own commit.
- **No existing artifact was restyled** (D30), including this repo's s00–s02.
- **S7** as above.
