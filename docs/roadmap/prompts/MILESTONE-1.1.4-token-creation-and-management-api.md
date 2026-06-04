# Milestone 1.1.4 — Execution Prompt: Token Creation and Management API

Copy this prompt into your AI tool (Cursor, Codex, etc.) to implement the milestone. Do not add agent attribution to commits or PRs.

---

You are acting as **Principal Engineer + Security Owner** for IBEX Harness.

## Mission

Implement **Milestone 1.1.4: Token Creation and Management API** as defined in [../phase-1-core-platform/milestones/1.1.4-token-creation-and-management-api.md](../phase-1-core-platform/milestones/1.1.4-token-creation-and-management-api.md).

## You MUST read first

- [AGENTS.md](../../../AGENTS.md)
- [.cursorrules](../../../.cursorrules)
- [docs/adr/ADR-0005-postgres-migration-strategy.md](../../adr/ADR-0005-postgres-migration-strategy.md)
- [docs/adr/ADR-0006-auth-proto-contract.md](../../adr/ADR-0006-auth-proto-contract.md)
- [docs/adr/ADR-0007-auth-token-validation.md](../../adr/ADR-0007-auth-token-validation.md)
- [docs/adr/ADR-0009-permission-bitmap.md](../../adr/ADR-0009-permission-bitmap.md)
- [docs/SECURITY.md](../../SECURITY.md)
- [docs/TESTING_STRATEGY.md](../../TESTING_STRATEGY.md) §6
- [packages/permissions/permissions.go](../../../packages/permissions/permissions.go)
- [prompts/00-invariants.txt](../../../prompts/00-invariants.txt)

## Non-negotiable constraints

- **ADR-0007 PAT wire format** — do not use alternate base62 layouts from older draft text
- **Repository never stores plaintext** — hash only via `HashBearer`
- **Management RPC authz** — `authorization: Bearer` metadata; `ValidateToken` exempt
- **Never log plaintext or hash** — audit logs may include `prefix` and `token_id`
- **PR template** — fill all sections from `.github/pull_request_template.md`
- **PR-only** to `main`; no agent attribution

## Branch

`feature/m1-1-4-token-creation`

## PR title

`feat(auth): token creation and management (m1.1.4)`

## Verification commands

```bash
make proto-gen && make proto-test
go test ./services/auth/...
make compose-test-up
go test -tags=integration ./services/auth/...
make repo-guards
```

grpcurl (admin bearer in metadata):

```bash
grpcurl -plaintext -H "authorization: Bearer <admin-pat>" \
  -d '{"org_id":"<uuid>","name":"dev","type":1,"permissions":<bitmap>}' \
  localhost:9091 ibex.auth.v1.AuthService/CreateToken
```

---

*Reference: [roadmap README](../README.md)*
