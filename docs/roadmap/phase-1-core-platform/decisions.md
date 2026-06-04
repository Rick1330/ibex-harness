# Phase 1 — Decision Log

Quick decisions during Phase 1. Promote durable choices to `docs/adr/` when they affect multiple phases.

| Date | Decision | Rationale | ADR |
| --- | --- | --- | --- |
| 2026-06-01 | Roadmap lives under `docs/roadmap/` | Avoid new top-level dir; repo-guards unchanged | — |
| 2026-06-02 | Migration tool: golang-migrate + Go embed runner | Version-pinned in root `go.mod`; reproducible CI; `make db-migrate` via `go run` | [ADR-0005](../../adr/ADR-0005-postgres-migration-strategy.md) |
| 2026-06-03 | Auth package: `ibex.auth.v1` | Matches `ibex.context.v1`; `ValidateToken` only in v1 | [ADR-0006](../../adr/ADR-0006-auth-proto-contract.md) |
| 2026-06-03 | PAT wire format + service-account lookup | `ibex_pat_<uuid>_<secret>`; Argon2id PHC on full bearer; RLS bypass for lookup only | [ADR-0007](../../adr/ADR-0007-auth-token-validation.md) |
| 2026-06-03 | Integration Postgres: CI services vs local testcontainers | Required CI uses GHA service Postgres; local default is compose test (5433); `IBEX_USE_TESTCONTAINERS=1` for self-contained runs | — |
| 2026-06-04 | Permission bitmap layout locked | `packages/permissions`; Phase 2 proxy minimum `ProxyChatCompletion` | [ADR-0009](../../adr/ADR-0009-permission-bitmap.md) |
| 2026-06-04 | Token management gRPC + caller bearer authz | `CreateToken`/`RevokeToken`/`ListTokens`; metadata `authorization: Bearer` | [ADR-0006](../../adr/ADR-0006-auth-proto-contract.md) |
| 2026-06-04 | Cryptography policy centralized | `packages/crypto`; Argon2id PHC; production p=4 | [ADR-0010](../../adr/ADR-0010-cryptography-policy.md) |
| 2026-06-04 | Proxy auth gRPC client | ValidateToken middleware; fail closed | [ADR-0011](../../adr/ADR-0011-proxy-auth-client.md) |
| 2026-06-04 | Auth cache deferred to Phase 2 optional 2.2.1 | Correctness + SECURITY §15 before bloom/LRU; `TokenValidator` wrapper | [ADR-0011](../../adr/ADR-0011-proxy-auth-client.md) §7 |
| 2026-06-04 | Proxy chat body normalization | Parse-only; INVALID_JSON / 501 stub | [ADR-0012](../../adr/ADR-0012-proxy-request-normalization.md) |
| TBD | Token table subset first | `organizations` + `tokens` only for validate path | — |
| TBD | Proto gen: Option A uncommitted | Consistent with ADR-0004 | ADR-0004 |

## Pending decisions (resolve during milestones)

1. **gRPC port and TLS for local dev** — default insecure localhost for dev only; document production mTLS separately.
2. ~~**Permission bitmap minimal set**~~ — Resolved: `permissions.ProxyChatCompletion` per ADR-0009.
3. ~~**Integration test tagging**~~ — Resolved: `//go:build integration` for Postgres/RLS tests (see `infra/migrations/postgres`).
