# Milestone 1.2.1 — Execution Prompt: Proxy Auth Client and Middleware

Copy this prompt into your AI tool (Cursor, Codex, etc.) to implement the milestone. Do not add agent attribution to commits or PRs.

---

You are acting as **Principal Engineer + Security Owner** for IBEX Harness.

## Mission

Implement **Milestone 1.2.1: Proxy Auth Client and Middleware** as defined in [../phase-1-core-platform/milestones/1.2.1-proxy-auth-client.md](../phase-1-core-platform/milestones/1.2.1-proxy-auth-client.md).

## You MUST read first

- [AGENTS.md](../../../AGENTS.md) — §5 security, no token logging
- [.cursorrules](../../../.cursorrules) — §1.6.2 testing
- [docs/adr/ADR-0006-auth-proto-contract.md](../../adr/ADR-0006-auth-proto-contract.md)
- [docs/adr/ADR-0007-auth-token-validation.md](../../adr/ADR-0007-auth-token-validation.md)
- [docs/adr/ADR-0009-permission-bitmap.md](../../adr/ADR-0009-permission-bitmap.md)
- [docs/adr/ADR-0011-proxy-auth-client.md](../../adr/ADR-0011-proxy-auth-client.md)
- [docs/SECURITY.md](../../SECURITY.md) §15 fail closed
- [docs/API_DOCUMENTATION.md](../../API_DOCUMENTATION.md) — error codes
- [packages/permissions/permissions.go](../../../packages/permissions/permissions.go)
- [prompts/00-invariants.txt](../../../prompts/00-invariants.txt)

## Non-negotiable constraints

- **Fail closed** — auth down/timeout → HTTP 503; no cache bypass in v1
- **Never log bearer tokens** — may log `org_id`, `token_id` after success
- **`TokenValidator` interface** — cache wraps in Phase 2 optional 2.2.1
- **Layout:** `services/proxy/internal/auth/` per FILE_STRUCTURE.md (not `authclient/`)
- **PR body** from `ibex-harness-workspace/pr-bodies/`
- **PR-only** to `main`; no agent attribution

## Branch

`feature/m1-2-1-proxy-auth-client`

## PR title

`feat(proxy): auth gRPC client (m1.2.1)`

## Verification

```bash
make proto-gen
go test ./services/proxy/...
go test -tags=integration ./services/proxy/...
make repo-guards
golangci-lint run ./services/proxy/...
```

---

*Reference: [roadmap README](../README.md)*
