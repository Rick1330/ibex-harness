# Milestone 1.2.3 — Execution Prompt: Proxy Input Validation and Stable Error Envelope

Copy this prompt into your AI tool (Cursor, Codex, etc.) to implement the milestone. Do not add agent attribution to commits or PRs.

---

You are acting as **Principal Engineer** for IBEX Harness.

## Mission

Implement **Milestone 1.2.3: Proxy Input Validation and Stable Error Envelope** per [../phase-1-core-platform/milestones/1.2.3-proxy-input-validation-and-stable-error-envelope.md](../phase-1-core-platform/milestones/1.2.3-proxy-input-validation-and-stable-error-envelope.md) and [ADR-0013](../../adr/ADR-0013-proxy-input-validation-and-error-envelope.md).

## You MUST read first

- [AGENTS.md](../../../AGENTS.md) — §5 security; no prompt/content logging
- [ADR-0011](../../adr/ADR-0011-proxy-auth-client.md) — auth codes (**do not rename**)
- [ADR-0012](../../adr/ADR-0012-proxy-request-normalization.md) — parse vs validate split
- [ADR-0013](../../adr/ADR-0013-proxy-input-validation-and-error-envelope.md)
- [docs/API_DOCUMENTATION.md](../../API_DOCUMENTATION.md) — envelope, `X-IBEX-Agent-ID`
- [docs/SECURITY.md](../../SECURITY.md) §8.1
- [docs/DEVELOPMENT_GUIDE.md](../../DEVELOPMENT_GUIDE.md) — post-merge `--delete-branch`

## Non-negotiable constraints

- **No scope creep** — no rate limit (1.2.4), OTel exporter (1.3.1), provider HTTP, bloom cache
- **Single error writer** in `services/proxy/internal/errors/`
- **Body limit before parse** — `http.MaxBytesReader` on chat route
- **Keep auth codes** — `MISSING_TOKEN`, `INVALID_TOKEN`, `INSUFFICIENT_PERMISSIONS`, `SERVICE_DEGRADED`
- **Semantic validation** → **400** `VALIDATION_ERROR` with all `field_errors` aggregated
- **Fix context bug** — `r = r.WithContext(llm.WithChatRequest(...))`
- **PR body** from `ibex-harness-workspace/pr-bodies/pr-m123-proxy-input-validation.md`
- **Merge with** `gh pr merge <N> --squash --delete-branch`

## Branch

`feature/m1-2-3-input-validation`

## PR title

`feat(proxy): input validation and stable error envelope (m1.2.3)`

## Verification

```bash
make proto-gen
go test ./services/proxy/...
go test -tags=integration ./services/proxy/...
make repo-guards
golangci-lint run ./services/proxy/...
```

PowerShell chat smoke (no bash `\` continuations):

```powershell
$headers = @{
  Authorization = "Bearer <pat>"
  "Content-Type" = "application/json"
  "X-IBEX-Agent-ID" = "550e8400-e29b-41d4-a716-446655440000"
}
$body = '{"model":"gpt-4","messages":[{"role":"user","content":"hi"}]}'
Invoke-RestMethod -Uri http://localhost:8080/v1/chat/completions -Method POST -Headers $headers -Body $body
```
