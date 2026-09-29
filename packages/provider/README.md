# `packages/provider`

LLM provider abstraction, registry, capability catalog, and provider adapters.

## Contract and ownership

This is a shared package, not a deployable process. Consumers must preserve its tenant, authorization, error, and fail-closed boundaries; do not copy security-sensitive helpers into a service. Current implementation entry points include `breaker_isolation_test.go`, `breaker_wrap.go`, `breaker_wrap_test.go`, `capability.go`, `capability_catalog.go`, `capability_test.go`.

Status is **implemented in this repository** when source and tests are present; this README does not claim hosted production readiness. Changes that alter a cross-service contract require an ADR, consumer updates, and negative/tenant-isolation tests.

## Verification

From the repository root:

```bash
go test ./packages/provider/...
```

If this package has no direct Go test files, run the owning service’s prescribed test target and keep the package contract covered by a consumer test.
