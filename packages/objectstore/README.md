# `packages/objectstore`

Tenant-aware object storage interfaces and signed-object boundary helpers.

## Contract and ownership

This is a shared package, not a deployable process. Consumers must preserve its tenant, authorization, error, and fail-closed boundaries; do not copy security-sensitive helpers into a service. Current implementation entry points include `client.go`, `client_test.go`, `s3.go`.

Status is **implemented in this repository** when source and tests are present; this README does not claim hosted production readiness. Changes that alter a cross-service contract require an ADR, consumer updates, and negative/tenant-isolation tests.

## Verification

From the repository root:

```bash
go test ./packages/objectstore/...
```

If this package has no direct Go test files, run the owning service’s prescribed test target and keep the package contract covered by a consumer test.
