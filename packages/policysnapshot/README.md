# `packages/policysnapshot`

Signed `policy-snapshot.v1` envelope contract: JCS-canonical claims, RSA PKCS#1 v1.5 SHA-256 (RS256) signing and fail-closed verification against the AuthService policy-signing key set.

## Contract and ownership

This is a shared package, not a deployable process. It implements the authority accepted in the G0 owner decision record (`web/engineering/architecture-v2/21-g0-owner-decision-record.md` §2.1-2.2): AuthService is the sole issuer (`services/auth` `IssuePolicySnapshot`) and consumers verify locally before any effect. Entry points: `snapshot.go` (claims, envelope, digest, classification), `issuer.go`, `verifier.go`, `keys.go`.

Safety semantics:

- Authority must be `AuthService`; contract version must be `policy-snapshot.v1`; algorithm must be `RS256`.
- Payload must be JCS-canonical claims JSON; the `digest` field equals SHA-256 (lowercase hex) over the canonical claims with `digest` blanked.
- Keys must be RSA ≥ 2048 bits; unknown key ids fail closed; key rotation works by adding a new id and raising the minimum epoch.
- Freshness: accepted age is 30s for mutation/external effects and 60s for protected reads/context assembly, with 5s bounded clock skew; issued-in-the-future, age over the class bound, past `expires_at`, and `epoch < MinEpoch` all fail closed.
- Org and (when supplied) agent bindings must match the verified request scope.

Status is **implemented in this repository** when source and tests are present; this README does not claim hosted production readiness. Changes that alter the envelope or claims contract require an ADR update, consumer updates, and negative/cross-tenant tests.

## Verification

From the repository root:

```bash
go test ./packages/policysnapshot/...
go test ./services/auth/internal/grpc/ -run PolicySnapshot
go test ./services/proxy/internal/http/ -run PolicySnapshot
```

Consumers: `services/auth` (issuance), `services/proxy` (issuance fetch + verification middleware on protected routes).
