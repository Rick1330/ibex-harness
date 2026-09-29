# `packages/ratelimit`

Redis-backed hierarchical/org rate-limiting algorithms and configuration contracts.

## Contract and ownership

This is a shared package, not a deployable process. Consumers must preserve its tenant, authorization, error, and fail-closed boundaries; do not copy security-sensitive helpers into a service. Current implementation entry points include `config_event.go`, `config_key.go`, `config_publisher.go`, `config_store.go`, `config_subscriber.go`, `config_test.go`.

Status is **implemented in this repository** when source and tests are present; this README does not claim hosted production readiness. Changes that alter a cross-service contract require an ADR, consumer updates, and negative/tenant-isolation tests.

## Verification

From the repository root:

```bash
go test ./packages/ratelimit/...
```

If this package has no direct Go test files, run the owning service’s prescribed test target and keep the package contract covered by a consumer test.
