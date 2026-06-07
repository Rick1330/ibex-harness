# Milestone 1.3.2 — Execution Prompt: Prometheus Metric Catalog and Client Migration

Copy this prompt into your AI tool (Cursor, Codex, etc.) to implement the milestone. Do not add agent attribution to commits or PRs.

---

You are acting as **Principal Engineer** for IBEX Harness.

## Mission

Implement **Milestone 1.3.2: Prometheus Metric Catalog and Client Migration** per [../phase-1-core-platform/milestones/1.3.2-prometheus-metric-catalog.md](../phase-1-core-platform/milestones/1.3.2-prometheus-metric-catalog.md).

## Mandatory rules — read before coding

| Rule | File |
| --- | --- |
| Pre-push CI gates | [30-pre-push-ci-gates.mdc](../../../.cursor/rules/30-pre-push-ci-gates.mdc) |
| IBEX packages (metrics REQUIRED) | [29-ibex-packages.mdc](../../../.cursor/rules/29-ibex-packages.mdc) |
| Observability | [18-observability.mdc](../../../.cursor/rules/18-observability.mdc) |
| CodeScene / complexity | [21-complexity-management.mdc](../../../.cursor/rules/21-complexity-management.mdc) |
| PR workflow | [26-pr-git-workflow.mdc](../../../.cursor/rules/26-pr-git-workflow.mdc) |
| AGENTS.md | [AGENTS.md](../../../AGENTS.md) |

## Non-negotiable constraints

- All `prometheus.MustRegister` only in `packages/metrics`
- Route label = template (`r.Pattern` after handler), never raw URL path
- No `org_id`, `agent_id`, `user_id`, `session_id` labels
- Proxy validate timing removed; auth gRPC server owns `ibex_auth_validate_*` metrics
- **PR body** from `ibex-harness-workspace/pr-bodies/pr-m132-prometheus-metrics.md`
- **Merge with** `gh pr merge <N> --squash --delete-branch`
- Address all reviewer comments before merge

## Branch

`chore/m1-3-2-prometheus-metric-catalog`

## PR title

`chore(obs): prometheus client migration and canonical metric catalog (m1.3.2)`

## Verification

```powershell
Get-ChildItem -Recurse -Filter *.go packages/metrics,services/proxy,services/auth | ForEach-Object { gofmt -l $_.FullName }
go test ./packages/metrics/... -count=1
go test ./services/proxy/... -count=1
go test ./services/auth/... -count=1
make repo-guards
```
