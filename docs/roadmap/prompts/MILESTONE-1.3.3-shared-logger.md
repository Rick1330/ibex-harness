# Milestone 1.3.3 — Execution Prompt: Shared Structured Logger

Copy this prompt into your AI tool (Cursor, Codex, etc.) to implement the milestone. Do not add agent attribution to commits or PRs.

---

You are acting as **Principal Engineer** for IBEX Harness.

## Mission

Implement **Milestone 1.3.3: Shared Structured Logger Package** per [../phase-1-core-platform/milestones/1.3.3-shared-logger-package.md](../phase-1-core-platform/milestones/1.3.3-shared-logger-package.md).

## Mandatory rules — read before coding

| Rule | File |
| --- | --- |
| Pre-push CI gates | [30-pre-push-ci-gates.mdc](../../../.cursor/rules/30-pre-push-ci-gates.mdc) |
| IBEX packages (logger REQUIRED) | [29-ibex-packages.mdc](../../../.cursor/rules/29-ibex-packages.mdc) |
| Observability | [18-observability.mdc](../../../.cursor/rules/18-observability.mdc) |
| CodeScene / complexity | [21-complexity-management.mdc](../../../.cursor/rules/21-complexity-management.mdc) |
| PR workflow | [26-pr-git-workflow.mdc](../../../.cursor/rules/26-pr-git-workflow.mdc) |
| AGENTS.md | [AGENTS.md](../../../AGENTS.md) |

## Non-negotiable constraints

- **Only** `packages/logger` in `services/*` — no direct `log/slog` usage
- Mandatory JSON fields: `timestamp`, `level`, `service`, `request_id`, `trace_id`, `message`
- Forbidden fields redacted to `[REDACTED]`
- Logger passed by DI; no `slog.SetDefault`
- **PR body** from `ibex-harness-workspace/pr-bodies/pr-m133-shared-logger.md`
- **Merge with** `gh pr merge <N> --squash --delete-branch`

## Branch

`chore/m1-3-3-shared-logger`

## PR title

`chore(obs): shared structured logger package with mandatory field schema (m1.3.3)`

## Verification

```powershell
Get-ChildItem -Recurse -Filter *.go packages/logger,packages/shutdown,services/proxy,services/auth | ForEach-Object { gofmt -l $_.FullName }
go test ./packages/logger/... -count=1
go test ./packages/shutdown/... -count=1
go test ./services/proxy/... -count=1
go test ./services/auth/... -count=1
make repo-guards
```
