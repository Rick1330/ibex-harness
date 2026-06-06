# Milestone 1.2.4 — Execution Prompt: Proxy Rate Limit Skeleton

Copy this prompt into your AI tool (Cursor, Codex, etc.) to implement the milestone. Do not add agent attribution to commits or PRs.

---

You are acting as **Principal Engineer** for IBEX Harness.

## Mission

Implement **Milestone 1.2.4: Proxy Rate Limit Skeleton** per [../phase-1-core-platform/milestones/1.2.4-proxy-rate-limit-skeleton.md](../phase-1-core-platform/milestones/1.2.4-proxy-rate-limit-skeleton.md) and [ADR-0015](../../adr/ADR-0015-proxy-rate-limit-skeleton.md).

## You MUST read first

- [AGENTS.md](../../../AGENTS.md) — §5 security; no prompt/content logging
- [ADR-0011](../../adr/ADR-0011-proxy-auth-client.md) — auth codes (**do not rename**)
- [ADR-0013](../../adr/ADR-0013-proxy-input-validation-and-error-envelope.md) — middleware order (amended by ADR-0015)
- [ADR-0015](../../adr/ADR-0015-proxy-rate-limit-skeleton.md)
- [29-ibex-packages.mdc](../../../.cursor/rules/29-ibex-packages.mdc) — rate limit via `packages/ratelimit`
- [15-redis-patterns.mdc](../../../.cursor/rules/15-redis-patterns.mdc) — key format, fail-open

## Non-negotiable constraints

- **No scope creep** — no agent verification (1.2.5), OTel (1.3.1), Prometheus rate metrics (1.3.2), `packages/apierror` (1.4.2)
- **Redis logic in `packages/ratelimit` only** — proxy middleware calls `Limiter` interface
- **Fail open** on Redis errors; **fail closed** for auth (unchanged)
- **Middleware after auth** on protected routes only
- **429** with `RATE_LIMITED`, `Retry-After`, `X-RateLimit-*` headers
- **PR body** from `ibex-harness-workspace/pr-bodies/pr-m124-proxy-rate-limit-skeleton.md`
- **Merge with** `gh pr merge <N> --squash --delete-branch`

## Branch

`feature/m1-2-4-rate-limit-skeleton`

## PR title

`feat(proxy): rate limit skeleton (m1.2.4)`

## Verification

```bash
go test ./packages/ratelimit/...
go test ./services/proxy/...
go test -tags=integration ./services/proxy/...
make repo-guards
golangci-lint run ./packages/ratelimit/... ./services/proxy/...
```

PowerShell rate-limit smoke (requires Redis + auth + PAT):

```powershell
$headers = @{ Authorization = "Bearer <pat>" }
1..61 | ForEach-Object {
  Invoke-WebRequest -Uri http://localhost:8080/v1/internal/auth-probe -Headers $headers -UseBasicParsing
}
# expect 61st → 429 RATE_LIMITED
```
