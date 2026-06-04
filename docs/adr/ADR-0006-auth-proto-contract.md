# ADR-0006: Auth protobuf contract (`ibex.auth.v1`)

- **Status:** Accepted
- **Date:** 2026-06-03
- **Authors:** IBEX Harness team

## Context

Milestone 1.1.1 established Postgres schema for `ibex_core.tokens` and RLS. Milestones 1.1.3 (auth service) and 1.2.1 (proxy auth client) need a stable internal gRPC contract for token validation before implementation.

[ADR-0004](ADR-0004-protobuf-and-codegen-policy.md) defines Buf lint/breaking and uncommitted `gen/`. [ARCHITECTURE.md](../ARCHITECTURE.md) documents the auth validation pipeline: proxy calls auth on cache miss and expects `org_id`, optional `agent_id`, permission bitmap, and expiry.

## Decision

### 1) Package and file layout

- **Protobuf package:** `ibex.auth.v1`
- **Source file:** [packages/proto/proto/ibex/auth/v1/auth.proto](../../packages/proto/proto/ibex/auth/v1/auth.proto)
- **Layout:** Same pattern as `ibex.context.v1` under `packages/proto/proto/ibex/<domain>/v1/` ([FILE_STRUCTURE.md](../FILE_STRUCTURE.md) §4.1)

### 2) Service and RPCs (v1)

- **Service:** `AuthService`
- **RPCs:**
  - `ValidateToken` — proxy hot path; **no caller bearer required**
  - `CreateToken` — returns plaintext **once**; requires caller bearer with `TokenCreate` ([ADR-0009](ADR-0009-permission-bitmap.md))
  - `RevokeToken` — requires `TokenRevoke` or revoking caller's own `token_id`
  - `ListTokens` — metadata only (no hash/plaintext); requires `TokenCreate` for v1
- **Caller auth (management RPCs):** gRPC metadata `authorization: Bearer <pat>` validated via the same path as `ValidateToken`
- **Deferred:** JWT issuance, SSO exchange, Redis bloom invalidation RPCs

### 3) Messages

**ValidateTokenRequest**

- `access_token` (string): full value from `Authorization: Bearer ...` (e.g. `ibex_pat_...`). The auth service hashes and looks up internally; callers must not log this field.

**ValidateTokenResponse** (success)

- `org_id` (string): tenant UUID for `SET LOCAL app.current_org_id` in the auth service
- `permissions` (int64): 64-bit permission bitmap per [ARCHITECTURE.md](../ARCHITECTURE.md)
- `agent_id` (optional string): when the token is agent-scoped
- `user_id` (optional string): when the token is user-scoped
- `token_id` (optional string): `ibex_core.tokens.id` for audit/revocation
- `expires_at` (`google.protobuf.Timestamp`, optional): unset when the token is non-expiring

### 4) Error model

Use **standard gRPC status codes** only. Do not define REST-style error envelope messages in proto.

| Condition | gRPC code |
| --- | --- |
| Missing, malformed, unknown, revoked, or expired token | `Unauthenticated` |
| Valid token but insufficient permission for a later scoped operation | `PermissionDenied` (enforced by callers using `permissions`; not returned by successful `ValidateToken`) |
| Invalid create/list request fields | `InvalidArgument` |
| Token not found in org scope (revoke/list) | `NotFound` |
| Caller bearer missing on management RPC | `Unauthenticated` |

`ValidateToken` returns `OK` with populated `ValidateTokenResponse` when the token is valid and not revoked.

### 5) `go_package` and codegen

- **go_package:** `github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1;authv1`
- **Generated output:** `packages/proto/gen/` (gitignored per ADR-0004)
- **Plugins:** `protocolbuffers/go` + `grpc/go` in [buf.gen.yaml](../../packages/proto/buf.gen.yaml) for local `buf generate`
- **Local command:** `make proto-gen` (runs `buf generate` in `packages/proto`)
- **Contract tests:** `make proto-test` (unit); `make proto-test-integration` (requires buf; generates stubs ephemerally)
- **CI:** `buf lint` and `buf breaking` against `main`; `proto-contract` job runs ephemeral `buf generate` + contract tests — **`gen/` is never committed** (ADR-0004)

### 6) Consumers

| Milestone | Role |
| --- | --- |
| 1.1.3 | Auth service: implement `ValidateToken` server |
| 1.1.4 | Auth service: `CreateToken`, `RevokeToken`, `ListTokens` |
| 1.2.1 | Proxy: gRPC client + middleware |

## Consequences

### Positive

- Proxy and auth share a versioned, linted contract before service code lands.
- `buf breaking` protects downstream implementers from accidental breaks.

### Negative

- Developers must run `buf generate` locally before building auth/proxy against stubs.
- Adding grpc plugin affects all RPC protos locally (including context); acceptable for 1.1.3.

## Alternatives considered

| Option | Why not |
| --- | --- |
| REST-only auth validation | Proxy hot path uses gRPC per architecture |
| Embed errors in proto messages | Duplicates HTTP envelope; gRPC status is sufficient |
| Commit `gen/` | ADR-0004 policy; noisy diffs |

## References

- [ADR-0004](ADR-0004-protobuf-and-codegen-policy.md)
- [ADR-0005](ADR-0005-postgres-migration-strategy.md)
- [Milestone 1.1.2](../roadmap/phase-1-core-platform/milestones/1.1.2-auth-proto-and-codegen.md)
- [packages/proto/README.md](../../packages/proto/README.md)
