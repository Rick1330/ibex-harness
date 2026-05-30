# ADR-0004: Protobuf and code generation policy

- **Status:** Accepted
- **Date:** 2026-05-30
- **Authors:** IBEX Harness team

## Context

IBEX Harness uses protobuf as the internal contract source of truth ([FILE_STRUCTURE.md](../FILE_STRUCTURE.md) §4.1). The first contract is `ContextAssemblyService` in `ibex.context.v1`, defined in [API_DOCUMENTATION.md](../API_DOCUMENTATION.md). We need consistent linting, breaking-change detection, and a clear policy for generated code before services consume protos.

## Decision

### 1) Buf toolchain

- **Lint:** `buf lint` with `STANDARD` rules in [packages/proto](../../packages/proto).
- **Breaking:** `buf breaking` with `FILE` breaking rules against `main`:

  ```bash
  buf breaking --against "https://github.com/Rick1330/ibex-harness.git#branch=main,subdir=packages/proto"
  ```

- **CI:** Optional `buf-lint` job runs lint + breaking on pull requests (not a branch-protection required check until explicitly promoted).

### 2) Generated code — do not commit `gen/`

- **`packages/proto/gen/` is gitignored** and not produced in CI.
- Developers run `buf generate` locally when implementing a service that consumes protos.
- **Rationale:** No Go/Python/TS consumers exist yet; avoids noisy diffs and stale generated stubs. Revisit when the first service imports generated types (likely `services/proxy` or `services/context`).

### 3) Versioning and compatibility

- **Package path:** `ibex.<domain>.v1` (e.g. `ibex.context.v1`).
- **Field numbers:** Never reuse; reserve removed fields with `reserved`.
- **Additive changes only** within `v1`: new optional fields, new RPCs (with care).
- **Breaking changes** (rename, type change, required field, RPC removal): new package version (`v2`) or new service; align with [API_DOCUMENTATION.md](../API_DOCUMENTATION.md) API versioning policy.
- **`go_package`:** Set on protos for tooling; canonical Go module path finalized when root `go.mod` is added.

## Consequences

### Positive

- Contracts are reviewable, linted, and protected from accidental breaking edits.
- Clear handoff to service implementation PRs.

### Negative

- Consumers must run `buf generate` locally until CI generation is adopted.
- First proto PR establishes baseline; all future changes must pass `buf breaking`.

## References

- [packages/proto/README.md](../../packages/proto/README.md)
- [API_DOCUMENTATION.md](../API_DOCUMENTATION.md) — gRPC proto definition
- [ADR-0002](ADR-0002-repo-foundation-bootstrap.md)
