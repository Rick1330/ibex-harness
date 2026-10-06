# `packages/idempotency`

Tenant-scoped idempotency-store contract and request replay semantics.

## Contract and ownership

This is a shared package, not a deployable process. Consumers must preserve its tenant, authorization, error, and fail-closed boundaries; do not copy security-sensitive helpers into a service. Current implementation entry points include `redis.go`, `redis_bench_test.go`, `redis_test.go`, `store.go`.

Status is **implemented in this repository** when source and tests are present; this README does not claim hosted production readiness. Changes that alter a cross-service contract require an ADR, consumer updates, and negative/tenant-isolation tests.

The store rejects claims, commits, and releases without a non-zero `org_id`, non-blank key, or non-blank request fingerprint. This package-level guard is deliberate defense in depth: callers must not rely only on HTTP validation to preserve tenant scope.

## Verification

From the repository root:

```bash
go test ./packages/idempotency/...
```

If this package has no direct Go test files, run the owning service’s prescribed test target and keep the package contract covered by a consumer test.
