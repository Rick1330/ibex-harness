# Operator and MCP Surfaces

**Status:** `provisional` for current mounted surfaces; target contract below.

## Operator surface

The versioned management API is the authority-facing boundary. Console/BFF is the canonical operator client. Dashboard is compatibility-only. No UI writes databases directly.

Privileged actions—policy/directive promotion, token/key changes, provider credential changes, export, deletion, review/promotion, and rollback—require explicit permission/role, freshness, approval/MFA where required, idempotency, and durable evidence.

Readiness and diagnostics distinguish healthy, degraded, blocked, and uncertified. They do not expose secrets or cross-tenant existence.

## MCP surface

MCP is an external resource/tool boundary. It derives scope from authenticated principal, uses versioned tool descriptors and hashes, caps input/output, validates arguments, supports deadlines/cancellation, requires idempotency for writes, and records policy/evidence IDs. Tool descriptions and results are untrusted data.

Read-only tools precede write tools. Production stdio is disabled unless an explicit deployment profile and risk review enable it. MCP is not the identity provider; OAuth/IdP responsibility is documented at the deployment boundary.

### Read-only operator gateway (local, default-off)

`services/mcp-operator` (ADR-0086, issue #1013) mounts a Streamable HTTP MCP surface at `/mcp` only when `IBEX_MCP_OPERATOR_ENABLED=true`. It exposes four `read_only` tools — `session.get`, `run.get`, `evidence.query`, `budget.get` — each mapped to one typed scope over the existing permission bitmap (`operator.read`, `runs.read`, `evidence.read`, `budget.read`). Enforcement is shared with `packages/mcp_gateway` in this order: resolve tool → authorize → validate args → org rate limit → timed read → redact → audit.

Identity is token-derived only; tool schemas reject unknown arguments, so callers cannot supply `org_id` or agent identity. Reads run as `ibex_app` with `app.current_org_id` bound and an explicit `org_id` predicate; cross-tenant or missing rows return `not_found`, not `permission_denied`. Output is metadata-only (schema allowlist plus sensitive-key deny-list). Audit is metadata-only and non-blocking; durable rich-field audit is deferred.

Known limitation: Resource/action PolicySnapshot evaluation is not wired (no Python verifier). Authorization is a bitmap check behind a `PolicyEvaluator` seam. This keeps GAP-009 open and must not be read as policy-store enforcement or hosted operator readiness.
