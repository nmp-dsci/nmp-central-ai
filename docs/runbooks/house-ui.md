# Runbook — the house UI

One stylesheet gives every project in the portfolio the same look with its own colour.
Decisions: D25–D32 in [`AGENTS.md`](../../AGENTS.md). Contract: [`PLATFORM.md`](../../PLATFORM.md).

## The shape of it

```
nmp-central-ai/
  registry/projects.yaml        ui: {hue: N}        <- the only thing a project owns
  agent/house/house.css         the canon, v1       <- edit this
  agent/house/fonts/            IBM Plex, OFL 1.1
  scripts/house_ui.py           render · install · check · table
  scripts/house_ui_audit.py     the WCAG gate
```

Each project ends up with three things in its `.lavish/`:

```
house.css      byte-identical everywhere
project.css    one line:  :root{ --hue:80; }
fonts/         the five woff2 subsets + plex.css
```

and an artifact links two stylesheets:

```html
<link rel="stylesheet" href="house.css">
<link rel="stylesheet" href="project.css">
```

## Bring a project on board

1. Give it a hue in `registry/projects.yaml`, under `status:`:

   ```yaml
     - id: P9
       name: my-project
       path: ../my-project
       status: migrated
       ui:
         hue: 220        # must be 30 degrees from every other project's
   ```

2. `make house-ui` — refuses the registry if two hues are too close, then audits every
   accent in both themes and prints the table.
3. `make install-house-ui` — writes into that project's `.lavish/`. It writes into a
   **sibling repository**, so commit there separately.
4. In the project's artifacts, delete the inline `<style>` token block and link the two
   stylesheets. The class names the existing artifacts use (`wrap`, `tw`, `kpi`, `lead`,
   `chip`, `btn`, `dia`, …) are aliased in Layer 2b, so markup rarely needs touching.

## Change the house UI

1. Edit `agent/house/house.css`. If you add a colour, add a token — a component rule may
   not contain a raw hex — and add it to the `@contrast` block at the bottom if it has to
   be legible against anything.
2. Bump the version in the header comment (`nmp house UI v1` → `v2`). The stamp is what
   `house-ui-check` compares, so an un-bumped change looks current everywhere.
3. `make house-ui` — fails if any declared pair misses its ratio for any hue.
4. `make install-house-ui` — refuses a project whose copy was edited by hand; re-run with
   `FORCE=1` once you have looked at what was changed.
5. `make house-ui-check` — confirm every project reports `current`.

## Why one hue and not a hex

Every accent in the portfolio before this sat at OKLCH lightness 0.72–0.76 and chroma
0.10–0.13; only the hue varied. Making that explicit means contrast is guaranteed by
construction rather than by judgement: the light stop is `oklch(0.48 0.13 H)`, the dark
`oklch(0.78 0.13 H)`, and across the nine registered projects the worst ratio against any
surface is 5.33:1 against a 4.5 threshold.

A single hex cannot do this. Measured against the light background, *every* dark-theme
accent in the portfolio failed AA — the old house teal `#5cc8a6` scores 1.89:1.

## Gotchas

- **`--hue` only works on `:root`.** A custom property is substituted where it is
  *declared*, so an element that changes `--hue` lower down inherits the already-resolved
  `--accent`. `project.css` sets it on `:root`, which is why it works.
- **Status colours are not hue-derived.** `--amber`, `--red` and `--blue` are fixed: a
  warning must not change colour because a project picked a different brand. The audit
  refuses an accent that resolves to one of them (finding F7 — tau2-loop's accent used to
  *be* `--red`).
- **Hue separation does not apply to status hues.** Holding 30° clear of amber, red and
  blue as well would remove about half the wheel. Only project-to-project separation is
  enforced.
- **Fonts use relative paths.** The site's own `fonts.css` uses `/assets/fonts/…`, which
  only resolves from the site root. The vendored copy is rewritten to relative so an
  artifact works from `file://` and offline.

## Troubleshooting

| Symptom | Cause |
|---|---|
| `make house-ui` says two hues are within 30 degrees | pick another hue; `make house-ui` prints the table of what is taken |
| `install` says `DIFFERS … re-run with FORCE=1` | someone edited that project's copy; diff it against the canon before overwriting |
| `house-ui-check` says `BEHIND` | that project has an older version stamp; run `make install-house-ui` |
| an artifact renders unstyled from `file://` | it links `house.css` but the file is not beside it; `install` puts it there |
| the accent is the same in every project | `--hue` was set somewhere other than `:root`, or `project.css` is not linked after `house.css` |
