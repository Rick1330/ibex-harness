# packages/proto

Protobuf source of truth for IBEX Harness internal gRPC contracts.

## Layout

```text
proto/ibex/<domain>/v1/*.proto
```

Generated output (when run locally) goes to `gen/` and is **not committed** — see [ADR-0004](../../web/content/docs/adr/0004-protobuf-and-codegen-policy.mdx).

## Prerequisites

- [Buf CLI](https://buf.build/docs/installation)
- From repo root: `pnpm install` (pulls `@bufbuild/protobuf` for TypeScript stub type resolution via this package’s `package.json`)

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

`buf generate` emits:

| Output | Plugins |
| --- | --- |
| `gen/go/` | `protocolbuffers/go` + `grpc/go` |
| `gen/python/` | `protocolbuffers/python` |
| `gen/typescript/` | `bufbuild/es` (needs `@bufbuild/protobuf` from this workspace package for IDE/tsc) |

Generated files are **not committed** — see [ADR-0004](../../web/content/docs/adr/0004-protobuf-and-codegen-policy.mdx).

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
| `ibex.auth.v1` | `AuthService` (`ValidateToken`, `ValidateAgent`, `CreateToken`, `RevokeToken`, `ListTokens`) | [ADR-0006](../../web/content/docs/adr/0006-auth-proto-contract.mdx) |
