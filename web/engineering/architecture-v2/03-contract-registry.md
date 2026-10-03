# Contract Registry and Ownership

**Status:** `specified`; inventory must be completed before new boundary work.

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

## Compatibility rules

- Protobuf field numbers and names are never reused; removed fields are reserved.
- REST remains `/v1` until a deliberate major version; additive changes require examples and compatibility tests.
- MCP tool IDs, schemas, and result shapes are versioned and hashable.
- Provider aliases resolve to immutable deployment IDs before execution.
- Breaking changes require an ADR, migration, rollback/roll-forward plan, mixed-version tests, and docs.

CI must run Buf format/lint/generate/breaking checks, OpenAPI validation, golden error tests, MCP conformance, and generated-artifact reproducibility.
