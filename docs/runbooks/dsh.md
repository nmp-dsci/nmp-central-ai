# Runbook — DeepSeek Harness (D39)

DeepSeek Harness (`dsh`) is DeepSeek's open-source coding agent, a developer preview. Its
everyday front end here is the community **dsh-TUI**, which runs inside dsh in its own profile,
`~/.dsh/profiles/dsh-tui`. The plan of record is `.lavish/s07_deepseek-harness-plan.html`.

| piece | where |
|---|---|
| pinned versions | `DSH_VERSION`, `TUI_VERSION` in the Makefile |
| home patch (uploads off, plain session files) | `agent/dsh/home.cordis.patch.yml` → `~/.dsh/cordis.patch.yml` |
| user-global instructions | `agent/dsh/AGENTS.md` → `~/.dsh/AGENTS.md` |
| install, doctor, launcher | `scripts/dsh_doctor.py` |
| logger | `scripts/dsh_log.py` → MLflow experiment `dsh/sessions` |
| registry | entry `DSH`; its smoke replays `tests/fixtures/dsh` |

## First time

```bash
npm install -g pnpm            # dsh installs plugins with pnpm; Homebrew Node has no corepack
make dsh-install               # home patch first, then dsh and dsh-TUI at the pinned versions
make dsh-doctor                # every line ok except "API key" until the next step
make dsh-tui DIR=.             # first-run wizard: /provider → add your DeepSeek API key
```

Then, inside the TUI:

1. `Ctrl+P` shows the context loaded at startup. It must list `AGENTS.md` and the four
   `platform-*` skills.
2. `/model`, then `←/→` to lower the effort from *max* to *high*. dsh-TUI defaults to max.
3. Do the work. `Ctrl+D` twice exits.

Afterwards, `make dsh-log`.

## Every day

```bash
make dsh-tui DIR=../tau2-loop          # any repo inside ~/git/nmp-ai-portfolio
make dsh-web DIR=.                     # the browser UI on 127.0.0.1:3080, same sessions
make dsh-run DIR=. TASK="run the tests and summarise failures"
make dsh-log                           # copy finished turns into MLflow
make dsh-log ARGS="--dry-run"          # what would be logged, with cost estimates
```

Keys worth knowing: `@path` references a file, `Tab` completes or queues a follow-up,
`Esc Esc` rewinds to an earlier message, `Ctrl+C` interrupts, `Ctrl+O` shows full tool output,
`/resume` reopens a session, `/compact` frees context. **`Shift+Tab` cycles default → plan →
full-access; stay out of full-access**, which drops the approval prompts.

## Why the launcher, not `dsh` directly

dsh-TUI lives in its own profile, so plain `dsh` starts the default front end, not the TUI.
The TUI needs `dsh --profile dsh-tui`, and the launcher passes that flag for you:

| make target | runs |
|---|---|
| `make dsh-tui DIR=…` | `dsh --profile dsh-tui` |
| `make dsh-web DIR=…` | `dsh --profile web` |
| `make dsh-run DIR=… TASK=…` | `dsh --profile headless "…"` |

Typing `dsh --profile dsh-tui` yourself starts the same TUI, but skips everything below.

`make dsh-tui|dsh-web|dsh-run` run `scripts/dsh_doctor.py launch`, which:

- refuses any `DIR` outside the portfolio;
- checks dsh and dsh-TUI are at the pinned versions;
- composes the profile (`dsh --profile P --dump-config`, run from `DIR` so project-level config is seen) and refuses to start unless all three
  DeepSeek uploads are off. It matches rows by package name, so a renamed row is still caught;
- replaces itself with dsh under an empty environment: `HOME`, `PATH`, `LANG`, terminal
  variables, and `DSH_TELEMETRY_MODE=DISABLED`, `DSH_TELEMETRY_DISABLED=1`,
  `DSH_TUI_UPDATE_ENGINE=0`, `DSH_TUI_UPDATE_LAUNCHER=0`. The agent's shell inherits every
  non-`DSH_*` variable, so nothing from `~/.env` or your shell profile reaches it.

The three uploads dsh makes by default, and the home patch row that stops each:

| upload | row | home patch |
|---|---|---|
| the whole session log, on every DeepSeek API request | `session-log-deepseek` | `enabled: false` |
| the session log to DeepSeek's OTel collector on feedback | `session-telemetry-otel` | `mode: DISABLED` |
| installed plugin names and versions, on every request | `plugin-package-inventory-deepseek` | `enabled: false` |

Model requests themselves still carry whatever the agent reads. The user-global
`~/.dsh/AGENTS.md` tells it never to read `.env` or other credential files. That is an
instruction, not a sandbox, which is one more reason to use dsh only on portfolio repos.

## Logging

One run per session (tags `project=dsh`, `workspace`, `dsh.session_id`; metrics for turns,
steps, tool calls and errors, tokens by kind, `cost_usd_est`, model, tool and wall seconds) and
one trace per finished turn (an LLM span per model call, a TOOL span per tool call). A rerun
starts after run tag `dsh.through_seq`, so it never duplicates. A turn still running waits.

Never logged: sessions outside the portfolio (only their header is read), reasoning text,
attachments, injected context, the result of a tool call that names `.env*`, `*.pem` or a
credentials file, and secret values. Every value in `~/.env` and anything shaped like an
`sk-`, `AKIA`, GitHub or Slack key, a private key, `NAME_KEY=…`, or a URL password becomes
`[redacted]`. Each field is cut to 4 KB.

Cost is an estimate from the dated price table in `scripts/dsh_log.py` (DeepSeek doubles the
price 01:00–04:00 and 06:00–10:00 UTC on weekdays). A model missing from the table counts in
`unpriced_calls`; add it with the date you read the price.

## Upgrading

Never use dsh-TUI's `/update` or `dsh-tui update`: they move both versions at once. Instead:

1. read dsh-TUI's changelog and check its supported dsh range;
2. bump `TUI_VERSION` (and `DSH_VERSION` if needed) in the Makefile;
3. `make dsh-install && make dsh-doctor`;
4. if the session format changed (the doctor reports formats the logger can't read), extend
   `scripts/dsh_log.py` and its fixture before logging again.

## Troubleshooting

| symptom | fix |
|---|---|
| `refusing …: dsh runs only inside …` | pass a `DIR` inside `~/git/nmp-ai-portfolio` |
| `FAIL …: enabled is True, needs False` | the home patch is missing or a row moved: `make dsh-install`, then read the dump |
| `MISSING_CREDENTIAL` | the key isn't stored: start `make dsh-tui` and use `/provider` |
| `ERR_PNPM_IGNORED_BUILDS` during install | approve the listed builds once (dsh-TUI's getting-started guide), re-run `make dsh-install` |
| doctor: `unreadable formats {5: …}` | dsh moved to a new session format; see Upgrading step 4 |

## Uninstall

`npm uninstall -g @deepseek-ai/dsh`, then `rm -rf ~/.dsh` (sessions included; run
`make dsh-log` first). The MLflow experiment stays.
