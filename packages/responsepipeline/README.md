# `packages/responsepipeline`

Chat response decode/stage/re-encode pipeline and metadata-stage contract.

## Contract and ownership

This is a shared package, not a deployable process. Consumers must preserve its tenant, authorization, error, and fail-closed boundaries; do not copy security-sensitive helpers into a service. Current implementation entry points include `bench_test.go`, `chat_response.go`, `errors.go`, `ibex_metadata.go`, `ibex_metadata_test.go`, `noop.go`.

Status is **implemented in this repository** when source and tests are present; this README does not claim hosted production readiness. Changes that alter a cross-service contract require an ADR, consumer updates, and negative/tenant-isolation tests.

## Verification

From the repository root:

```bash
go test ./packages/responsepipeline/...
```

If this package has no direct Go test files, run the owning service’s prescribed test target and keep the package contract covered by a consumer test.
