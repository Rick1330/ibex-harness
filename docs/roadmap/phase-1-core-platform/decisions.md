# Phase 1 — Decision Log

Quick decisions during Phase 1. Promote durable choices to `docs/adr/` when they affect multiple phases.

| Date | Decision | Rationale | ADR |
| --- | --- | --- | --- |
| 2026-06-01 | Roadmap lives under `docs/roadmap/` | Avoid new top-level dir; repo-guards unchanged | — |
| 2026-06-02 | Migration tool: golang-migrate + Go embed runner | Version-pinned in root `go.mod`; reproducible CI; `make db-migrate` via `go run` | [ADR-0005](../../adr/ADR-0005-postgres-migration-strategy.md) |
| 2026-06-03 | Auth package: `ibex.auth.v1` | Matches `ibex.context.v1`; `ValidateToken` only in v1 | [ADR-0006](../../adr/ADR-0006-auth-proto-contract.md) |
| TBD | Token table subset first | `organizations` + `tokens` only for validate path | — |
| TBD | Proto gen: Option A uncommitted | Consistent with ADR-0004 | ADR-0004 |

## Pending decisions (resolve during milestones)

1. **gRPC port and TLS for local dev** — default insecure localhost for dev only; document production mTLS separately.
2. **Permission bitmap minimal set** — which bits required for proxy chat completion in Phase 2 vs stub all-required for Phase 1.
3. ~~**Integration test tagging**~~ — Resolved: `//go:build integration` for Postgres/RLS tests (see `infra/migrations/postgres`).
