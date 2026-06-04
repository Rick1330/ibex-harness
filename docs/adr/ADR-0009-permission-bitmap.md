# ADR-0009: Permission bitmap layout

- **Status:** Accepted
- **Date:** 2026-06-04
- **Authors:** IBEX Harness team

## Context

The 64-bit permission bitmap is stored on `ibex_core.tokens.permissions` and returned by `ValidateToken`. Multiple docs reference the layout, but no single Go package or ADR locked the bit assignments. Milestone 1.1.5 establishes the contract before token management (1.1.4) and proxy auth (1.2.1) enforce permission checks.

## Decision

### 1) Canonical implementation

- **Package:** `packages/permissions` (`github.com/Rick1330/ibex-harness/packages/permissions`)
- **Helpers:** `Has`, `HasAny`, `RequiresMFA`, `UsesReservedHighBits`
- **Predefined sets:** `AgentDefault`, `ProxyChatCompletion`, `ReadOnly`, `Admin`

### 2) Bit layout (v1)

| Bit | Group | Permission |
| --- | --- | --- |
| 0 | Memory | `MemoryRead` |
| 1 | Memory | `MemoryWrite` |
| 2 | Memory | `MemoryDelete` |
| 3 | Memory | `MemoryBulkExport` |
| 4-7 | Memory | Reserved |
| 8 | Directive | `DirectiveRead` |
| 9 | Directive | `DirectiveWrite` |
| 10 | Directive | `DirectivePromote` (MFA) |
| 11 | Directive | `DirectiveRevoke` (MFA) |
| 12-15 | Directive | Reserved |
| 16 | Session | `SessionCreate` |
| 17 | Session | `SessionRead` |
| 18 | Session | `SessionTerminate` |
| 19-23 | Session | Reserved |
| 24 | Trace | `TraceRead` |
| 25 | Trace | `TraceExport` |
| 26-31 | Trace | Reserved |
| 32 | Admin | `UserManage` |
| 33 | Admin | `BillingRead` |
| 34 | Admin | `BillingManage` |
| 35 | Admin | `OrgSettingsWrite` |
| 36 | Admin | `TokenCreate` |
| 37 | Admin | `TokenRevoke` |
| 38-39 | Admin | Reserved |
| 40 | Marketplace | `MarketplacePublish` |
| 41 | Marketplace | `MarketplaceInstall` |
| 42-47 | Marketplace | Reserved |
| 48 | Federation | `FederationShare` |
| 49-55 | Federation | Reserved |
| 56-63 | — | Reserved (do not use in v1) |

### 3) Phase 2 proxy minimum

For OpenAI-compatible chat completion through the proxy, a token must include:

`MemoryRead | SessionCreate | SessionRead` (`permissions.ProxyChatCompletion`).

### 4) Change policy

- Bit positions are stable for `ibex.auth.v1` and stored token rows.
- New permissions consume reserved bits within a group or require ADR + migration if layout changes.
- Bits 56-63 are reserved for future expansion.

## Consequences

### Positive

- Single import path for all services checking permissions.
- Tests verify non-overlap and subset relationships.

### Negative

- Renumbering bits requires data migration and a new ADR.

## References

- [ARCHITECTURE.md](../ARCHITECTURE.md) — auth permission table
- [Milestone 1.1.5](../roadmap/phase-1-core-platform/milestones/1.1.5-permission-bitmap-contract-and-adr.md)
- [ADR-0006](ADR-0006-auth-proto-contract.md) — `ValidateTokenResponse.permissions`
