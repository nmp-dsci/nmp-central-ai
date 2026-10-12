# Runbook — AWS demos: sleep, wake, and what never to delete (D37)

The portfolio AWS account runs four always-on App Runner demos. At one minimum instance each
they cost about $25 a month before GST, which was 95% of the bill on 2026-10-12. Everything else in
the account costs cents. The plan of record is `.lavish/s05_aws-pause-plan.html`.

| project | service | region | deploy workflow |
|---|---|---|---|
| P1 convfinqa-agent | `convfinqa-demo` | ap-southeast-1 | `nmp-dsci/ConvFinQA-agent` · `deploy-aws.yml` |
| P2 dabstep-loop | `dabstep-demo` | ap-southeast-1 | `nmp-dsci/DABStep-loop` · `deploy-aws.yml` |
| P4 transcript-rag-agent | `yt-agent-demo` | ap-southeast-2 | `nmp-dsci/transcript-rag-agent` · `deploy-aws.yml` |
| P5 data-qa-agent | `data-qa-demo` | ap-southeast-2 | `nmp-dsci/data-qa-agent` · `deploy-aws.yml` |

The registry's `aws_demo:` blocks are the source of truth for this table.

## Commands

```bash
aws sso login --profile <profile>     # once per session
export AWS_PROFILE=<profile>

make demos-status                     # state, deploy workflow, URL
make demos-sleep                      # workflow off, then pause; waits for PAUSED
make demos-wake                       # resume, wait for RUNNING, then workflow on
make demos-wake ARGS="--only P5"      # one demo
make demos-sleep ARGS="--dry-run"     # print the plan only
```

Both commands are idempotent, so running one against a demo already in that state does nothing.
Waking takes a few minutes per service. They resume in parallel.

- Sleep skips a demo whose deploy workflow state it cannot read (`gh` missing, logged out or
  erroring), so nothing is paused with its workflow still on. Fix `gh` and re-run.
- `make demos-wake ARGS="--no-wait"` returns once the resume is issued. Deploys stay off until
  the service is `RUNNING`; re-run `make demos-wake` then, and it only enables the workflow.

## Why it works this way

- **Pause, never delete.** A paused service bills no compute and keeps its `*.awsapprunner.com`
  URL and its image. The portfolio site links to all four URLs, and so does
  `DABStep-loop/README.md`. A deleted service comes back on a new URL. App Runner also closed to
  new customers on 2026-04-30 and does not define what makes an account "existing", so we keep
  the services in the account rather than test that.
- **The workflow goes off first.** App Runner rejects `StartDeployment` and `UpdateService` on a
  paused service. Each `deploy-aws.yml` polls for `RUNNING` 60 × 20 s and then fails, and
  data-qa's `start-deployment` fails outright. Sleep refuses to pause a demo while a deploy run
  is in progress.
- **The workflow comes back on last.** Wake enables it only once the service is `RUNNING`.
- **Resume restores the old image.** It brings back the version that was live before the pause,
  even with auto-deploy on. If `main` moved while the demo slept, run the deploy once:
  `gh workflow run deploy-aws.yml -R <repo>`.
- In-memory state, such as chat sessions, starts fresh after a resume.

## Keep these: cheap, and hard or impossible to recreate

| item | why |
|---|---|
| ECR repos (5, ~8.5 GB, lifecycle keeps 5 images) | resume and redeploys need them; ~$0.66/mo |
| Aurora snapshot `data-qa-aurora-pre-dbless-20260922` | the only copy of the retired data-qa database |
| S3 `yt-agent-demo-data-*` | Chroma index + knowledge-graph snapshot, not in git |
| S3 `data-qa-tfstate-*` (+ table `data-qa-tf-lock`) | Terraform state for six stacks in five repos |
| CloudFront `deqfc8b0u8s64.cloudfront.net` | the live data-pilot URL |
| IAM OIDC provider `token.actions.githubusercontent.com` + `*-github-deploy` roles | every repo's CI assumes them |

## Still open

- **The $1/mo auto-deploy fee.** AWS does not say whether paused services pay it.
  `convfinqa-demo`, `dabstep-demo` and `yt-agent-demo` have auto-deploy on. Check the November
  bill (`aws ce get-cost-and-usage … --group-by Type=DIMENSION,Key=USAGE_TYPE`, look for
  `*-AppRunner-AutomaticDeployment`). If it still bills, set `auto_deployments_enabled = false`
  in those three Terraform stacks at the next wake. A changed apply cannot run while paused.
- **App Runner is being wound down** (no new features). Moving the demos to ECS Express Mode is
  planned as M5 in `ai_specs/s00_project_plan.md`.
