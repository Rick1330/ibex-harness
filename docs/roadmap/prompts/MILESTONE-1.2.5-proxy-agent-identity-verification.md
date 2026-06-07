# Milestone 1.2.5 — Execution Prompt: Proxy Agent Identity Verification

Copy this prompt into your AI tool (Cursor, Codex, etc.) to implement the milestone. Do not add agent attribution to commits or PRs.

---

You are acting as **Principal Engineer** for IBEX Harness.

## Mission

Implement **Milestone 1.2.5: Proxy Agent Identity Verification** per [../phase-1-core-platform/milestones/1.2.5-proxy-agent-identity-verification.md](../phase-1-core-platform/milestones/1.2.5-proxy-agent-identity-verification.md) and [ADR-0016](../../adr/ADR-0016-agent-identity-verification.md).

## You MUST read first

- [AGENTS.md](../../../AGENTS.md) — §5 security; no prompt/content logging
- [ADR-0011](../../adr/ADR-0011-proxy-auth-client.md) — auth codes (**do not rename** `SERVICE_DEGRADED` for token validate)
- [ADR-0013](../../adr/ADR-0013-proxy-input-validation-and-error-envelope.md) — error envelope (amended by ADR-0016)
- [ADR-0015](../../adr/ADR-0015-proxy-rate-limit-skeleton.md) — middleware order (amended by ADR-0016)
- [ADR-0016](../../adr/ADR-0016-agent-identity-verification.md)
- [28-multitenant-security.mdc](../../../.cursor/rules/28-multitenant-security.mdc) — 403 not 404 for cross-org

## Non-negotiable constraints

- **No scope creep** — no `packages/apierror` (1.4.2), no ValidateAgent caching (Phase 2), no OTel (1.3.1)
- **Middleware order:** `Auth → AgentVerification → RateLimit → handler` on all protected routes
- **Fail closed** on agent verify gRPC failure → 503 `AUTH_UNAVAILABLE`
- **Required** `X-IBEX-Agent-ID` on all protected Phase-1 routes (auth-probe + chat)
- **org_id from token** only — never from header/body for ValidateAgent call
- **Forward bearer** in gRPC metadata for ValidateAgent (auth interceptor requires it)
- **PR body** from `ibex-harness-workspace/pr-bodies/pr-m125-proxy-agent-identity-verification.md`
- **Merge with** `gh pr merge <N> --squash --delete-branch`

## Branch

`feature/m1-2-5-agent-identity-verification`

## PR title

`feat(proxy): agent identity verification via gRPC ValidateAgent (m1.2.5)`

## Verification

```bash
make proto-gen
go test ./services/proxy/...
go test -tags=integration ./services/proxy/...
make repo-guards
golangci-lint run ./services/proxy/...
```

PowerShell smoke (requires Postgres + auth + proxy + seeded agent):

```powershell
$headers = @{
  Authorization = "Bearer <pat>"
  "X-IBEX-Agent-ID" = "<agent-uuid>"
}
Invoke-WebRequest -Uri http://localhost:8080/v1/internal/auth-probe -Headers $headers -UseBasicParsing
# Without agent header → 400 MISSING_AGENT_ID
```
