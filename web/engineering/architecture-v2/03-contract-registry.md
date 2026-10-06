# Contract Registry and Ownership

**Status:** `specified`; inventory must be completed before new boundary work. The initial G0 registry packet is proposed in ADR-0084 and tracked by issue #933; no G0 exit is claimed.

## Contract hierarchy

- **Protobuf/gRPC:** internal multi-consumer service contracts.
- **OpenAPI/REST:** external management and resource APIs under `/v1`.
- **Provider contracts:** separately versioned Chat Completions and Responses subsets plus native adapter semantics.
- **MCP schemas:** versioned tools/resources with explicit scopes and limits.
- **Events:** durable evidence and operation envelopes.
- **Database schemas:** lifecycle and authority contracts, not merely ORM models.

## Required registry fields

| Field | Required |
|---|---|
| Contract ID and owner | Yes |
| Source path and generated artifacts | Yes |
| Version and compatibility class | Yes |
| Auth/permission/resource scope | Yes |
| Status class and deployment profile | Yes |
| Error and retry behavior | Yes |
| Idempotency/deadline/cancellation | Where applicable |
| Tests and evidence link | Yes |
| Deprecation/support window | Public contracts |
|---|---|

## Proposed G0 registrations

The following registrations are the first review packet for the principal and replay foundation. They remain `proposed` until G0 owners approve the authority, compatibility, profile, and evidence fields.

| Contract ID and owner | Source path and generated artifacts | Version / status | Scope and failure behavior | Tests and evidence |
|---|---|---|---|---|
| `principal-context.v1` — Auth/Proxy | `packages/proto/proto/ibex/auth/v1/auth.proto`; proxy/auth request context | v1 / proposed | Verified org and subject context; token-bound agent mismatch denies before lookup; missing verifier fails staging/production router construction | `agent_middleware_test.go`, `validate_agent_test.go`, `router_must_test.go`; profile evidence pending |
| `run-envelope.v1` — Architecture/Proxy | Architecture-v2 principal/run contract; additive boundary mapping pending G0 | v1 / specified, not implemented | Correlation and lineage only; resume/retry revalidates principal, policy, resource, and approval state | Cross-boundary contract matrix pending |
| `idempotency-operation.v1` — Platform/Data | Existing operation-specific idempotency stores; durable schema pending G0 | v1 / proposed | Tenant-bound key and canonical body hash; same body replays, changed body conflicts, ambiguous completion reconciles by operation ID | Operation-specific crash/replay suites pending |

## Compatibility rules

- Protobuf field numbers and names are never reused; removed fields are reserved.
- REST remains `/v1` until a deliberate major version; additive changes require examples and compatibility tests.
- MCP tool IDs, schemas, and result shapes are versioned and hashable.
- Provider aliases resolve to immutable deployment IDs before execution.
- Breaking changes require an ADR, migration, rollback/roll-forward plan, mixed-version tests, and docs.

CI must run Buf format/lint/generate/breaking checks, OpenAPI validation, golden error tests, MCP conformance, and generated-artifact reproducibility.
