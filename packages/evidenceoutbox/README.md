# `packages/evidenceoutbox`

Tenant/evidence-scoped transactional outbox and durable evidence writer contracts.

## Contract and ownership

This is a shared package, not a deployable process. Consumers must preserve its tenant, authorization, error, and fail-closed boundaries; do not copy security-sensitive helpers into a service. Current implementation entry points include `doc.go`, `relay.go`, `relay_backoff_test.go`, `relay_unit_test.go`, `schema_compat_test.go`, `store.go`.

Status is **implemented in this repository** when source and tests are present; this README does not claim hosted production readiness. Changes that alter a cross-service contract require an ADR, consumer updates, and negative/tenant-isolation tests.

Before a claimed row reaches a projection sink, the relay validates its tenant, event, aggregate, schema, payload, and digest identity. Invalid rows are not delivered; they enter the existing failed/poison path so integrity failures remain observable and recoverable rather than becoming silent sink writes.

## Verification

From the repository root:

```bash
go test ./packages/evidenceoutbox/...
```

If this package has no direct Go test files, run the owning service’s prescribed test target and keep the package contract covered by a consumer test.
