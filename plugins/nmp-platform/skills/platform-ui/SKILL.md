---
name: platform-ui
description: Style a Lavish artifact, HTML page, report or review surface in any nmp-ai-portfolio project with the shared house UI. Use when writing or editing a .lavish/ artifact, when about to author a <style> block of design tokens, colours, fonts, spacing or dark mode, when asked to match the house look or a project's colour, or when touching house.css, project.css or registry ui.hue.
---

# platform-ui

The portfolio has ONE house UI. A project owns exactly one thing about its look: an
integer hue. Contract: `~/git/nmp-ai-portfolio/nmp-central-ai/PLATFORM.md` (House UI table).
Runbook: `nmp-central-ai/docs/runbooks/house-ui.md`. Decisions: D25–D32.

## Facts

- The canon is `nmp-central-ai/agent/house/house.css`. Every project holds a byte-identical
  copy at `<project>/.lavish/house.css`, installed by `make -C …/nmp-central-ai install-house-ui`.
- Beside it sit `project.css` (one line, generated: `:root{ --hue:N; }`) and `fonts/`
  (IBM Plex, self-hosted, OFL 1.1).
- Tokens cover colour in **light and dark**, a type scale (`--t-2`…`--t6`), a 4/8 spacing
  ladder (`--s1`…`--s10`), `--r`, `--shadow`, `--measure`, `--dur`/`--ease`, `--focus`.
- Components: `card cards split badge tag stat verdict callout tablewrap steps kv eyebrow
  lede sub fig qgrid`, plus aliases the older artifacts use: `wrap tw kpi lead chip chips
  btn label small top dia fig-title grid v-ok sr-only`.

## Writing an artifact

Link two stylesheets and write no token block at all:

```html
<link rel="stylesheet" href="house.css">
<link rel="stylesheet" href="project.css">
```

Then use the classes above. If `.lavish/house.css` is not there yet, the project has not
been onboarded — run `make -C ~/git/nmp-ai-portfolio/nmp-central-ai install-house-ui`
(it writes into this repo; commit it here).

## Rules

1. **Never write a `:root{ --bg:… }` token block into an artifact.** That is the thing the
   house UI exists to stop. 277 artifacts already carry 39,894 lines of it.
2. **Never put a raw hex in a rule.** Use a token. A colour that does not exist as a token
   is a change to `house.css` plus a `@contrast` line, not a literal in one file.
3. **Never hand-edit a vendored `.lavish/house.css`.** It is generated; the next
   `install-house-ui` refuses it, and `make house-ui-check` reports it as drift. Change the
   canon instead.
4. **Never pick a colour for a project.** Add `ui: {hue: N}` to `registry/projects.yaml`
   and let both theme stops be generated. Hues must be 30° apart; `make house-ui` refuses
   a registry that breaks that and prints what is taken.
5. **Do not override `--hue` anywhere but `:root`.** Custom properties resolve where they
   are declared, so a nested override inherits the already-resolved accent and nothing
   changes colour.
6. **Status colours are fixed.** `--amber` warning, `--red` error, `--blue` information do
   not follow the brand. Do not use the accent for a status, or a status colour as a brand.
7. **Do not restyle an existing artifact** unless asked. They are dated receipts (D30).

## Checks

```bash
make -C ~/git/nmp-ai-portfolio/nmp-central-ai house-ui         # render + WCAG gate + table
make -C ~/git/nmp-ai-portfolio/nmp-central-ai house-ui-check   # which copies are stale
```

A failing gate names the theme, the project, the hue and the pair that missed its ratio.
Fix the token, not the threshold.
