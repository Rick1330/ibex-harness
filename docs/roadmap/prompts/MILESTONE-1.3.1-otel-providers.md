# Milestone 1.3.1 — Execution Prompt: OTel Tracer and Meter Provider Init

Copy this prompt into your AI tool (Cursor, Codex, etc.) to implement the milestone. Do not add agent attribution to commits or PRs.

---

You are acting as **Principal Engineer** for IBEX Harness.

## Mission

Implement **Milestone 1.3.1: OTel Tracer and Meter Provider Initialization** per [../phase-1-core-platform/milestones/1.3.1-otel-tracer-provider-init.md](../phase-1-core-platform/milestones/1.3.1-otel-tracer-provider-init.md).

## Mandatory rules — read before coding

| Rule | File |
| --- | --- |
| Pre-push CI gates | [30-pre-push-ci-gates.mdc](../../../.cursor/rules/30-pre-push-ci-gates.mdc) |
| IBEX packages (telemetry REQUIRED) | [29-ibex-packages.mdc](../../../.cursor/rules/29-ibex-packages.mdc) |
| Observability | [18-observability.mdc](../../../.cursor/rules/18-observability.mdc) |
| CodeScene / complexity | [21-complexity-management.mdc](../../../.cursor/rules/21-complexity-management.mdc) |
| PR workflow | [26-pr-git-workflow.mdc](../../../.cursor/rules/26-pr-git-workflow.mdc) |
| AGENTS.md | [AGENTS.md](../../../AGENTS.md) |

## Non-negotiable constraints

- Tracer from `providers.TracerProvider.Tracer(...)` — no `otel.Tracer()` in services
- HTTP span names use route template (`r.Pattern`), not raw URL path
- `Providers.Shutdown` registered FIRST on `packages/shutdown.Coordinator`
- Synthetic UUID `X-Trace-ID` retired — use OTel span trace ID (ADR-0017 §5)
- **PR body** from `ibex-harness-workspace/pr-bodies/pr-m131-otel-providers.md`
- **Merge with** `gh pr merge <N> --squash --delete-branch`

## Branch

`chore/m1-3-1-otel-providers`

## PR title

`chore(obs): OTel tracer and meter provider init with HTTP span middleware (m1.3.1)`

## Verification

```powershell
Get-ChildItem -Recurse -Filter *.go packages/telemetry,packages/shutdown,services/proxy,services/auth | ForEach-Object { gofmt -l $_.FullName }
go test ./packages/telemetry/... -count=1
go test ./packages/shutdown/... -count=1
go test ./services/proxy/... -count=1
go test ./services/auth/... -count=1
make repo-guards
```
