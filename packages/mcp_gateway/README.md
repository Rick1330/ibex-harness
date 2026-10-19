# mcp_gateway (Python)

Shared, transport-agnostic **enforcement core** for the read-only IBEX MCP
operator gateway (GAP-009). The deployable MCP surface lives in
`services/mcp-operator`; this package owns the authorization vocabulary and the
ordered enforcement pipeline so authorization logic is unit-testable without a
transport.

## What it owns

- **Typed scopes** (`scopes.py`) — named aliases over the existing permission
  bitmap (`packages/permissions`): `operator.read`→`OPERATOR_METADATA_READ`,
  `runs.read`→`TRACE_READ`, `evidence.read`→`OPERATOR_REDACTED_READ`,
  `budget.read`→`BILLING_READ`.
- **Tool registry** (`registry.py`) — versioned `ToolSpec` (read-only only),
  JSON-Schema descriptors with `additionalProperties: false`, and a canonical
  `sha256:` descriptor hash that binds the published surface to a stable digest.
- **Policy seam** (`policy.py`) — `PolicyEvaluator` protocol with a
  `BitmapPolicyEvaluator`. A configured-but-unavailable authority denies; it
  never allows. This is the single point a future Python PolicySnapshot verifier
  attaches to.
- **Redaction** (`redaction.py`) — positive-list output sanitizer (schema
  allowlist plus a sensitive-name deny-list); a missing required field fails
  closed.
- **Enforcement** (`enforcement.py`) — the ordered, deny-by-default pipeline:
  tool resolve → policy → schema validation → rate limit → timed read → redact →
  audit (never blocks the read).
- **Audit** (`audit.py`) — metadata-only `ToolAuditEvent` plus a non-blocking
  `AsyncAuditEmitter`. Contains no payload content.

## Failure taxonomy

| Condition | Code | HTTP-equivalent |
| --- | --- | --- |
| Unknown tool | `tool_not_found` | 404 |
| Missing scope / policy deny | `permission_denied` | 403 |
| Policy authority unavailable | `policy_unavailable` | 403 |
| Malformed arguments | `invalid_params` | 400 |
| Rate limit exceeded | `rate_limited` | 429 |
| Rate-limit authority down | `rate_limit_unavailable` | 503 |
| Read backend down / timeout | `backend_unavailable` | 503 |
| Output could not be redacted | `redaction_failed` | 500 |

## Consumers

`services/mcp-operator`. The intended second consumer is the eventual
convergence of `services/mcp-memory` onto the same enforcement core.

## Tests

```bash
cd packages/mcp_gateway
uv sync --extra dev
.venv/bin/ruff check .
.venv/bin/pytest -q
```
