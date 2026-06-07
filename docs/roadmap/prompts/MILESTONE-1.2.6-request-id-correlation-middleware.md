# Milestone 1.2.6 — Execution Prompt: Request ID Correlation Middleware

Copy this prompt into your AI tool (Cursor, Codex, etc.) to implement the milestone. Do not add agent attribution to commits or PRs.

---

You are acting as **Principal Engineer** for IBEX Harness.

## Mission

Implement **Milestone 1.2.6: Request ID Generation and Correlation Middleware** per [../phase-1-core-platform/milestones/1.2.6-request-id-correlation-middleware.md](../phase-1-core-platform/milestones/1.2.6-request-id-correlation-middleware.md) and [ADR-0017](../../adr/ADR-0017-request-id-strategy.md).

## You MUST read first

- [AGENTS.md](../../../AGENTS.md) — §5 security; no prompt/content logging
- [ADR-0013](../../adr/ADR-0013-proxy-input-validation-and-error-envelope.md) — error envelope + response headers (amended by ADR-0017)
- [ADR-0016](../../adr/ADR-0016-agent-identity-verification.md) — middleware order
- [ADR-0017](../../adr/ADR-0017-request-id-strategy.md)
- [30-pre-push-ci-gates.mdc](../../../.cursor/rules/30-pre-push-ci-gates.mdc) — local CI before push
- [21-complexity-management.mdc](../../../.cursor/rules/21-complexity-management.mdc) — CodeScene limits

## Non-negotiable constraints

- **Do not re-implement** existing `RequestContextMiddleware` / `ResponseHeadersMiddleware` — refactor in place
- **No scope creep** — no OTel (1.3.1), no W3C traceparent, no auth-side logging (1.3.3)
- **UUID v7** for generated IDs; honour valid inbound UUID v4/v7; reject garbage
- **`packages/reqid`** owns context key; proxy `http` layer thin-wraps
- **gRPC interceptor** on auth client conn propagates `x-request-id` (do not duplicate in verifiers)
- **PR body** from `ibex-harness-workspace/pr-bodies/pr-m126-request-id-correlation.md`
- **Merge with** `gh pr merge <N> --squash --delete-branch`

## Branch

`feature/m1-2-6-request-id-middleware`

## PR title

`feat(proxy): request ID generation and context correlation middleware (m1.2.6)`

## Verification

```bash
go test ./packages/reqid/...
go test ./services/proxy/...
go test -tags=integration ./services/proxy/...
make repo-guards
```

PowerShell pre-push gate:

```powershell
Get-ChildItem -Recurse -Filter *.go packages/reqid,services/proxy | ForEach-Object { gofmt -l $_.FullName }
go test ./packages/reqid/... -count=1
go test ./services/proxy/... -count=1
```
