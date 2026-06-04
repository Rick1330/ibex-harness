# ADR-0013: Proxy input validation and stable error envelope

- **Status:** Accepted
- **Date:** 2026-06-02
- **Authors:** IBEX Harness team

## Context

Milestone 1.2.2 parses OpenAI-shaped chat JSON after auth with an **unbounded** body read and a minimal error envelope. Goal 1.2 requires security boundaries (body size, Content-Type), semantic validation with `field_errors`, and consistent response headers before rate limiting (1.2.4) and provider HTTP (Phase 2).

## Decision

### 1) Limits (security controls; ADR amendment to change)

| Constant | Value |
| --- | --- |
| `MaxRequestBodyBytes` | 1 MiB |
| `MaxMessagesPerRequest` | 1000 |
| `MaxMessageContentBytes` | 100 KiB |
| `MaxModelNameLength` | 256 |
| `MaxChatMaxTokens` | 1_048_576 |
| Temperature (when set) | 0.0–2.0 inclusive |

### 2) HTTP mapping

| Condition | HTTP | `code` |
| --- | --- | --- |
| Body exceeds limit | 413 | `PAYLOAD_TOO_LARGE` |
| Wrong `Content-Type` on chat POST | 415 | `UNSUPPORTED_MEDIA_TYPE` |
| Semantic / header validation | 400 | `VALIDATION_ERROR` + `field_errors` |
| Malformed JSON (parse) | 400 | `INVALID_JSON` (unchanged) |
| Auth failures | 401/403/503 | `MISSING_TOKEN`, `INVALID_TOKEN`, `INSUFFICIENT_PERMISSIONS`, `SERVICE_DEGRADED` (ADR-0011; **no renames**) |
| Valid request, no provider | 501 | `PROVIDER_NOT_CONFIGURED` |
| Wrong HTTP method (JSON routes) | 405 | `METHOD_NOT_ALLOWED` |

### 3) Field error codes (canonical)

`REQUIRED`, `TOO_LONG`, `TOO_MANY`, `INVALID_ENUM`, `INVALID_FORMAT`

### 4) Content-Type

`POST /v1/chat/completions` requires `Content-Type: application/json` (allows `application/json; charset=utf-8`).

### 5) IBEX headers (chat)

- `X-IBEX-Agent-ID` **required**; value must be a UUID (v4/v7) via `github.com/google/uuid`
- Optional session header format checks deferred unless specified in API doc

### 6) Envelope

Single package `services/proxy/internal/errors`:

- `Detail` includes optional `docs_url`, `field_errors`
- All proxy JSON errors use `errors.Write` / `WriteFromRequest`
- Optional docs URL pattern: `{IBEX_ERROR_DOCS_BASE}/errors/{CODE}` (empty base omits `docs_url`)

### 7) Request / trace IDs

- `RequestContextMiddleware` (outer chain): accept incoming request ID header or generate UUID; generate `trace_id` per request until OTel (1.3.1)
- `AuthMiddleware` **reuses** request ID from context (fallback generate for isolated tests)
- `ResponseHeadersMiddleware`: sets request ID, trace ID, and `X-Response-Time` (ms) on every response
- Header names configurable: `IBEX_REQUEST_ID_HEADER` (default `X-Request-ID`), `IBEX_TRACE_ID_HEADER` (default `X-Trace-ID`)

### 8) Middleware order

```text
metrics → requestContext → responseHeaders → logging → mux

POST /v1/chat/completions:
  bodyLimit → contentType → auth → handler

GET /v1/orgs/{org_id}/auth-probe:
  pathOrgUUID → auth → handler
```

Milestone **1.2.4** inserts `rateLimit` **after auth**, before handler (document only; not implemented in 1.2.3).

Amends [ADR-0012](ADR-0012-proxy-request-normalization.md) §6 footnote accordingly.

### 9) Packages

- `internal/validation/` — limits, chat semantic validation, header validation
- `internal/http/middleware.go` — body limit, content-type, request context, response headers
- Extend `internal/errors/` — do **not** add `internal/http/errors.go`

### 10) Deferred / out of scope

- Redis rate limit (**1.2.4**)
- OTel exporter (**1.3.1**)
- Multimodal `content` arrays (string-only until Phase 2+)
- Bloom/LRU auth cache (**2.2.1**)
- Provider HTTP (`upstream/`)

## Consequences

### Positive

- Completes Goal 1.2 validation and stable envelope criteria on the proxy
- DoS risk from unbounded bodies closed before JSON decode
- Single error writer; auth codes stable for clients

### Negative

- Platform `/health` and `/ready` success payloads remain minimal `{status}`; **errors** use stable envelope
- Trace IDs are synthetic until 1.3.1

## References

- [Milestone 1.2.3](../roadmap/phase-1-core-platform/milestones/1.2.3-proxy-input-validation-and-stable-error-envelope.md)
- [ADR-0011](ADR-0011-proxy-auth-client.md)
- [ADR-0012](ADR-0012-proxy-request-normalization.md)
- [API_DOCUMENTATION.md](../API_DOCUMENTATION.md)
- [SECURITY.md](../SECURITY.md) §8.1
