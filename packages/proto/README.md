# packages/proto

Protobuf source of truth for IBEX Harness internal gRPC contracts.

## Layout

```text
proto/ibex/<domain>/v1/*.proto
```

Generated output (when run locally) goes to `gen/` and is **not committed** — see [ADR-0004](../../docs/adr/ADR-0004-protobuf-and-codegen-policy.md).

## Prerequisites

- [Buf CLI](https://buf.build/docs/installation)

## Commands

From this directory (`packages/proto`):

```bash
# Lint
buf lint

# Breaking changes vs main (after packages/proto exists on main; skipped on initial import PR)
buf breaking --against "https://github.com/Rick1330/ibex-harness.git#branch=main,subdir=packages/proto"

# Generate stubs (local only; output under gen/)
buf generate

# Or from repository root:
make proto-gen
```

`buf generate` emits Go messages and gRPC stubs (`protocolbuffers/go` + `grpc/go`) under `gen/go/`. Generated files are **not committed** — see [ADR-0004](../../docs/adr/ADR-0004-protobuf-and-codegen-policy.md).

## Contract tests

From repository root:

```bash
make proto-test              # unit: ADR-0006 descriptor assertions (no buf generate)
make proto-test-integration  # integration: buf generate + gRPC stub smoke (requires buf)
```

CI runs both in the `proto-contract` job (ephemeral `buf generate`; `gen/` must not appear in git).

## Contracts

| Package | Service | Source doc |
|---------|---------|------------|
| `ibex.context.v1` | `ContextAssemblyService` | [API_DOCUMENTATION.md](../../web/engineering/API_DOCUMENTATION.md) (gRPC section) |
| `ibex.auth.v1` | `AuthService` (`ValidateToken`) | [ADR-0006](../../docs/adr/ADR-0006-auth-proto-contract.md) |
