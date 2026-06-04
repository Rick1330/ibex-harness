# Milestone 1.2.2 — Execution Prompt: Proxy Request Normalization

Copy this prompt into your AI tool (Cursor, Codex, etc.) to implement the milestone. Do not add agent attribution to commits or PRs.

---

You are acting as **Principal Engineer** for IBEX Harness.

## Mission

Implement **Milestone 1.2.2: Proxy Request Normalization** per [../phase-1-core-platform/milestones/1.2.2-proxy-request-normalization.md](../phase-1-core-platform/milestones/1.2.2-proxy-request-normalization.md).

## You MUST read first

- [AGENTS.md](../../../AGENTS.md) — §5 security; no prompt/content logging
- [ADR-0011](../../adr/ADR-0011-proxy-auth-client.md) — auth middleware order
- [ADR-0012](../../adr/ADR-0012-proxy-request-normalization.md)
- [docs/API_DOCUMENTATION.md](../../API_DOCUMENTATION.md) — chat completions shape
- [docs/SECURITY.md](../../SECURITY.md) §10.1
- [services/proxy/internal/http/router.go](../../../services/proxy/internal/http/router.go)

## Non-negotiable constraints

- **Parse only** — no semantic validation (empty model OK until 1.2.3)
- **No provider HTTP** — valid parse → **501** `PROVIDER_NOT_CONFIGURED`
- **Malformed JSON** → **400** `INVALID_JSON` via `internal/errors`
- **Never log message content** — metadata only
- **Do not** implement body size / Content-Type middleware (1.2.3)
- **PR body** from `ibex-harness-workspace/pr-bodies/`

## Branch

`feature/m1-2-2-proxy-request-normalization`

## PR title

`feat(proxy): request normalization (m1.2.2)`

## Verification

```bash
go test ./services/proxy/...
go test -tags=integration ./services/proxy/...
make repo-guards
```
