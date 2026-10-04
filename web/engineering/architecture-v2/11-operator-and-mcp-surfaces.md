# Operator and MCP Surfaces

**Status:** `provisional` for current mounted surfaces; target contract below.

## Operator surface

The versioned management API is the authority-facing boundary. Console/BFF is the canonical operator client. Dashboard is compatibility-only. No UI writes databases directly.

Privileged actions—policy/directive promotion, token/key changes, provider credential changes, export, deletion, review/promotion, and rollback—require explicit permission/role, freshness, approval/MFA where required, idempotency, and durable evidence.

Readiness and diagnostics distinguish healthy, degraded, blocked, and uncertified. They do not expose secrets or cross-tenant existence.

## MCP surface

MCP is an external resource/tool boundary. It derives scope from authenticated principal, uses versioned tool descriptors and hashes, caps input/output, validates arguments, supports deadlines/cancellation, requires idempotency for writes, and records policy/evidence IDs. Tool descriptions and results are untrusted data.

Read-only tools precede write tools. Production stdio is disabled unless an explicit deployment profile and risk review enable it. MCP is not the identity provider; OAuth/IdP responsibility is documented at the deployment boundary.
