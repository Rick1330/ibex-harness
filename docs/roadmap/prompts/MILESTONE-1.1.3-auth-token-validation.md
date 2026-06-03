# Milestone 1.1.3 — Execution Prompt: Auth Token Validation

Copy this prompt into your AI tool (Cursor, Codex, etc.) to implement the milestone. Do not add agent attribution to commits or PRs.

---

You are acting as **Principal Engineer + Security Owner** for IBEX Harness.

## Mission

Implement **Milestone 1.1.3: Auth Token Validation** as defined in [../phase-1-core-platform/milestones/1.1.3-auth-token-validation.md](../phase-1-core-platform/milestones/1.1.3-auth-token-validation.md).

## You MUST read first

- [AGENTS.md](../../../AGENTS.md)
- [.cursorrules](../../../.cursorrules)
- [docs/adr/ADR-0005-postgres-migration-strategy.md](../../adr/ADR-0005-postgres-migration-strategy.md)
- [docs/adr/ADR-0006-auth-proto-contract.md](../../adr/ADR-0006-auth-proto-contract.md)
- [docs/adr/ADR-0007-auth-token-validation.md](../../adr/ADR-0007-auth-token-validation.md)
- [docs/ARCHITECTURE.md](../../ARCHITECTURE.md) — auth validation pipeline
- [docs/SECURITY.md](../../SECURITY.md) — Argon2id, no token logging
- [docs/TESTING_STRATEGY.md](../../TESTING_STRATEGY.md) §6.2 — auth tests
- [docs/FILE_STRUCTURE.md](../../FILE_STRUCTURE.md) §3.1 — Go service layout
- [packages/proto/proto/ibex/auth/v1/auth.proto](../../../packages/proto/proto/ibex/auth/v1/auth.proto)
- [docs/roadmap/phase-1-core-platform/milestones/1.2.1-proxy-auth-client.md](../phase-1-core-platform/milestones/1.2.1-proxy-auth-client.md)
- [prompts/00-invariants.txt](../../../prompts/00-invariants.txt)

If any file is inaccessible, STOP and ask for it.

## Non-negotiable constraints

- **Auth service only** — no proxy changes, no JWT issuance, no token creation API
- **No committed `packages/proto/gen/`** — run `make proto-gen` locally; CI generates ephemerally
- **Never log raw tokens** — not in code, tests, or fixtures committed to git
- **Fail closed** — invalid/revoked/expired/unknown → `codes.Unauthenticated` only (ADR-0006/0007)
- **RLS:** lookup uses `app.is_service_account = 'true'`; integration test proves cross-tenant isolation
- **PR-only** to `main`; required CI: `repo-guards`, `markdownlint`, `gitleaks`
- **No agent attribution** in commits or PR description

## Branch

`feature/m1-1-3-auth-validate-token`

## PR title (example)

`feat(auth): validate PAT against Postgres (m1.1.3)`

## Deliverables

1. gRPC `ValidateToken` server wired in `services/auth`
2. PAT parse + Argon2id verify + Postgres lookup per ADR-0007
3. Unit tests (parser, hash, handler) + integration tests (Postgres, cross-tenant)
4. CI `auth-validate-smoke` job (advisory)
5. `services/auth/README.md` grpcurl examples; `ENVIRONMENT_VARIABLES.md` + `.env.example`

## Definition of done

- Valid seeded PAT returns `ValidateTokenResponse` with correct `org_id` and `permissions`
- Invalid/revoked tokens return `Unauthenticated` without existence leak
- `go test ./services/auth/...` and `go test -tags=integration ./services/auth/...` pass
- `/health` and `/ready` unchanged in behavior
- Required CI green

## Verification commands

```bash
make compose-dev-up && make db-migrate
make proto-gen
go test ./services/auth/...
go test -tags=integration ./services/auth/...
IBEX_PORT=8081 IBEX_GRPC_PORT=9091 POSTGRES_DSN=postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable go run ./services/auth/cmd/auth
grpcurl -plaintext -d '{"access_token":"<pat>"}' localhost:9091 ibex.auth.v1.AuthService/ValidateToken
make repo-guards lint-docs
```

## After merge

Update [docs/roadmap/CURRENT_STATE.md](../CURRENT_STATE.md): SHA, 1.1.3 complete, next 1.2.1.

---

*Reference: [roadmap README](../README.md)*
