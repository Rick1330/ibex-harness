---
title: "ADR-0004: Protobuf and code generation policy"
description: "Architecture decision record 0004."
adrId: "0004"
status: "Accepted"
date: "2026-05-30"
authors: "IBEX Harness team"
---

::decision-banner{status="Accepted" date="2026-05-30" id="0004"}
::

# ADR-0004: Protobuf and code generation policy

- **Status:** Accepted
- **Date:** 2026-05-30
- **Authors:** IBEX Harness team

## Context

IBEX Harness uses protobuf as the internal contract source of truth ([FILE_STRUCTURE.md](https://github.com/Rick1330/ibex-harness/blob/main/engineering/FILE_STRUCTURE.md) §4.1). The first contract is `ContextAssemblyService` in `ibex.context.v1`, defined in [API_DOCUMENTATION.md](/docs/api-reference/http-routes). We need consistent linting, breaking-change detection, and a clear policy for generated code before services consume protos.

## Decision

### 1) Buf toolchain

- **Lint:** `buf lint` with `STANDARD` rules in [packages/proto](https://github.com/Rick1330/ibex-harness/tree/main/packages/proto).
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
- **Breaking changes** (rename, type change, required field, RPC removal): new package version (`v2`) or new service; align with [API_DOCUMENTATION.md](/docs/api-reference/http-routes) API versioning policy.
- **`go_package`:** Set on protos for tooling; canonical Go module path finalized when root `go.mod` is added.

## Consequences

### Positive

- Contracts are reviewable, linted, and protected from accidental breaking edits.
- Clear handoff to service implementation PRs.

### Negative

- Consumers must run `buf generate` locally until CI generation is adopted.
- First proto PR establishes baseline; all future changes must pass `buf breaking`.

## References

- [packages/proto/README.md](https://github.com/Rick1330/ibex-harness/tree/main/packages/proto/readme)
- [API_DOCUMENTATION.md](/docs/api-reference/http-routes) — gRPC proto definition
- [ADR-0002](https://github.com/Rick1330/ibex-harness/blob/main/engineering/adr/0002-repo-foundation-bootstrap.md)
