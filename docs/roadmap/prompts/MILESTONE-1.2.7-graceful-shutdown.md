# Milestone 1.2.7 — Execution Prompt: Graceful Shutdown

Copy this prompt into your AI tool (Cursor, Codex, etc.) to implement the milestone. Do not add agent attribution to commits or PRs.

---

You are acting as **Principal Engineer** for IBEX Harness.

## Mission

Implement **Milestone 1.2.7: Graceful Shutdown and Connection Draining** per [../phase-1-core-platform/milestones/1.2.7-graceful-shutdown.md](../phase-1-core-platform/milestones/1.2.7-graceful-shutdown.md) and [ADR-0018](../../adr/ADR-0018-graceful-shutdown.md).

## Mandatory rules — read before coding

| Rule | File |
| --- | --- |
| Pre-push CI gates | [30-pre-push-ci-gates.mdc](../../../.cursor/rules/30-pre-push-ci-gates.mdc) |
| CodeScene / complexity | [21-complexity-management.mdc](../../../.cursor/rules/21-complexity-management.mdc) |
| Architecture layering | [20-architecture-layering.mdc](../../../.cursor/rules/20-architecture-layering.mdc) |
| IBEX packages (shutdown REQUIRED) | [29-ibex-packages.mdc](../../../.cursor/rules/29-ibex-packages.mdc) |
| Config management | [24-config-management.mdc](../../../.cursor/rules/24-config-management.mdc) |
| Concurrency | [03-go-concurrency.mdc](../../../.cursor/rules/03-go-concurrency.mdc) |
| PR workflow | [26-pr-git-workflow.mdc](../../../.cursor/rules/26-pr-git-workflow.mdc) |
| AGENTS.md | [AGENTS.md](../../../AGENTS.md) |

## Non-negotiable constraints

- **Replace ad-hoc signal handling** in proxy/auth `main.go` with `packages/shutdown.Coordinator`
- **SIGTERM** → graceful drain within `IBEX_SHUTDOWN_TIMEOUT` (default `30s`)
- **SIGINT** → immediate shutdown (zero drain)
- **Exit 0** clean; **exit 1** on drain timeout exceeded
- **No scope creep** — no OTel shutdown (M1.3.1), no K8s preStop hooks
- **PR body** from `ibex-harness-workspace/pr-bodies/pr-m127-graceful-shutdown.md`
- **Merge with** `gh pr merge <N> --squash --delete-branch`

## Branch

`feature/m1-2-7-graceful-shutdown`

## PR title

`feat(infra): graceful shutdown with connection draining for auth and proxy (m1.2.7)`

## Verification

```powershell
Get-ChildItem -Recurse -Filter *.go packages/shutdown,services/proxy,services/auth | ForEach-Object { gofmt -l $_.FullName }
go test ./packages/shutdown/... -count=1
go test ./services/proxy/... -count=1
go test ./services/auth/... -count=1
make repo-guards
```
