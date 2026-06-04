# IBEX Harness - Complete API Documentation

## 🎯 API Design Philosophy

### Core Principles

1. **Predictable**: Every endpoint follows the same patterns. Learn one endpoint, understand all of them.

2. **Explicit over implicit**: Error responses tell you exactly what went wrong and how to fix it. No cryptic error codes.

3. **Versioned from day one**: Breaking changes never affect existing integrations. Old versions supported for 12 months minimum after deprecation notice.

4. **Idempotent where possible**: Safe to retry on network failure. Every write operation accepts an idempotency key.

5. **Consistent pagination**: Every list endpoint uses the same cursor-based pagination. No offset pagination (breaks at scale and with concurrent writes).

6. **Performance transparent**: Every response includes timing headers so clients can debug latency issues.

---

## 🌐 Base URLs

```text
Production:    https://api.ibexharness.com
Staging:       https://api.staging.ibexharness.com
Local Dev:     http://localhost:8000
LLM Proxy:     https://proxy.ibexharness.com (separate service)
Local Proxy:   http://localhost:8080
```

---

## 🔑 Authentication

### API Key Authentication (SDK and CLI)

```http
Authorization: Bearer ibex_pat_7f3k2m9x...
```

All SDK and programmatic API calls use Bearer token authentication. Tokens are created via the dashboard or CLI.

### Session Token Authentication (Dashboard)

```http
Authorization: Bearer eyJhbGciOiJSUzI1NiJ9...
X-IBEX-Session: {session_id}
```

Dashboard sessions use short-lived JWT tokens (1 hour) with automatic refresh via the refresh token flow.

### Request Signing (Webhooks)

Outbound webhooks are signed with HMAC-SHA256:

```http
X-IBEX-Signature: sha256={hmac_hex}
X-IBEX-Timestamp: 1705312445
```

Verify: `HMAC-SHA256(secret, timestamp + "." + body)`

---

## 📋 Common Patterns

### Request Headers

```http
Authorization: Bearer {token}          -- Required
Content-Type: application/json         -- Required for POST/PUT/PATCH
X-Idempotency-Key: {uuid}             -- Optional, recommended for writes
X-Request-ID: {uuid}                   -- Optional, for tracing
Accept-Language: en                    -- Optional, for error messages
```

### Response Headers

```http
X-Request-ID: {uuid}                   -- Echo of request ID
X-Trace-ID: {trace_id}                -- Distributed trace ID
X-RateLimit-Limit: 1000               -- Requests allowed per minute
X-RateLimit-Remaining: 987            -- Requests remaining this window
X-RateLimit-Reset: 1705312500         -- Unix timestamp when window resets
X-Response-Time: 42ms                 -- Server processing time
X-IBEX-Version: 1.2.3                 -- API server version
```

### Pagination (Cursor-Based)

All list endpoints use cursor pagination:

```http
GET /v1/memories?limit=50&cursor=eyJpZCI6IjEyMyJ9
```

Response:

```json
{
  "data": [...],
  "pagination": {
    "has_more": true,
    "next_cursor": "eyJpZCI6IjE3MyJ9",
    "prev_cursor": "eyJpZCI6IjcyIn0",
    "total_count": 1247
  }
}
```

**Why cursor over offset:**

- Offset breaks when items are inserted/deleted during pagination
- Cursor is stable: always returns correct next page
- Cursor is efficient: no COUNT(*) needed (expensive at scale)

### Error Response Format

Every error uses this structure:

```json
{
  "error": {
    "code": "MEMORY_NOT_FOUND",
    "message": "Memory with ID '550e8400-...' not found",
    "detail": "The memory may have been deleted or you may not have permission to access it.",
    "docs_url": "https://docs.ibexharness.com/errors/MEMORY_NOT_FOUND",
    "request_id": "req_7f3k2m9x",
    "timestamp": "2024-01-15T10:30:45.123Z",
    "field_errors": null
  }
}
```

**Validation errors** include field-level details:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed",
    "detail": "One or more fields failed validation",
    "field_errors": [
      {
        "field": "content",
        "code": "REQUIRED",
        "message": "content is required and cannot be empty"
      },
      {
        "field": "confidence",
        "code": "RANGE_ERROR",
        "message": "confidence must be between 0 and 1, got 1.5"
      }
    ]
  }
}
```

### Standard Error Codes

```text
HTTP 400 - Bad Request
  VALIDATION_ERROR         -- Request body/params failed validation
  INVALID_JSON             -- Malformed JSON in request body
  MISSING_REQUIRED_FIELD   -- Required field not provided
  INVALID_FIELD_VALUE      -- Field value out of allowed range/enum

HTTP 401 - Unauthorized
  MISSING_TOKEN            -- No Authorization header
  INVALID_TOKEN            -- Token not recognized
  EXPIRED_TOKEN            -- Token has expired
  REVOKED_TOKEN            -- Token has been revoked

HTTP 403 - Forbidden
  INSUFFICIENT_PERMISSIONS -- Token lacks required permission
  ORG_SUSPENDED            -- Organization account suspended
  QUOTA_EXCEEDED           -- Monthly quota exhausted
  TIER_RESTRICTION         -- Feature not available on current tier

HTTP 404 - Not Found
  {RESOURCE}_NOT_FOUND     -- Specific resource not found
  ROUTE_NOT_FOUND          -- API endpoint doesn't exist

HTTP 409 - Conflict
  DUPLICATE_CONTENT        -- Memory with same content exists
  VERSION_CONFLICT         -- Optimistic lock conflict
  STATE_CONFLICT           -- Resource in wrong state for operation

HTTP 422 - Unprocessable Entity
  CONTENT_TOO_LONG         -- Memory content exceeds limit
  EMBEDDING_FAILED         -- Could not generate embedding
  PII_DETECTED             -- PII detected, manual review required

HTTP 429 - Too Many Requests
  RATE_LIMIT_EXCEEDED      -- Per-minute rate limit hit
  DAILY_LIMIT_EXCEEDED     -- Daily request limit hit
  QUOTA_EXCEEDED           -- Monthly token quota exhausted

HTTP 500 - Internal Server Error
  INTERNAL_ERROR           -- Unexpected server error

HTTP 501 - Not Implemented
  PROVIDER_NOT_CONFIGURED  -- LLM provider not configured (Phase 1 proxy stub)
  DATABASE_ERROR           -- Database operation failed
  UPSTREAM_ERROR           -- External service error

HTTP 503 - Service Unavailable
  SERVICE_DEGRADED         -- Running in degraded mode
  MAINTENANCE_MODE         -- Planned maintenance window
```

### Idempotency Keys

For all POST requests that create or modify data:

```http
POST /v1/memories
X-Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000
```

**Behavior:**

- First request: Execute and cache result for 24 hours
- Duplicate request (same key, same endpoint): Return cached result
- Different endpoint with same key: Treated as different request
- Expired key (>24 hours): Execute normally

**Response includes idempotency status:**

```http
X-Idempotency-Replayed: false  -- true if returning cached result
```

---

## 🔌 API Reference

### API Version: v1

All endpoints prefixed with `/v1/`

---

## Memories API

### POST /v1/memories

**Create a memory**

Creates a new memory for an agent. Automatically handles deduplication, embedding generation, and conflict detection.

**Required Permission:** `memory:write`

**Request:**

```http
POST /v1/memories
Authorization: Bearer {token}
Content-Type: application/json
X-Idempotency-Key: {uuid}

{
  "agent_id": "550e8400-e29b-41d4-a716-446655440000",
  "content": "User prefers dark mode in all interfaces",
  "category": "preference",
  "confidence": 0.95,
  "session_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "visibility": "agent",
  "tags": ["ui", "preferences"],
  "metadata": {
    "source_url": "https://example.com",
    "extracted_at": "2024-01-15T10:30:00Z"
  }
}
```

**Request Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `agent_id` | UUID | Yes | Agent this memory belongs to |
| `content` | string | Yes | Memory content (1-10,000 chars) |
| `category` | enum | No | `factual`, `preference`, `behavioral`, `episodic`, `procedural`. Default: `factual` |
| `confidence` | float | No | 0.0-1.0. Default: 0.80 |
| `session_id` | UUID | No | Session this memory was created in |
| `visibility` | enum | No | `agent`, `org`, `session`. Default: `agent` |
| `tags` | string[] | No | Searchable tags. Max 20 tags, 50 chars each |
| `metadata` | object | No | Arbitrary JSON metadata. Max 10KB |
| `pinned` | boolean | No | Always include in context. Default: false |

**Response: 201 Created**

```json
{
  "data": {
    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "agent_id": "550e8400-e29b-41d4-a716-446655440000",
    "org_id": "123e4567-e89b-12d3-a456-426614174000",
    "content": "User prefers dark mode in all interfaces",
    "content_tokens": 8,
    "category": "preference",
    "confidence": 0.95,
    "source": "user_provided",
    "status": "active",
    "visibility": "agent",
    "pinned": false,
    "tags": ["ui", "preferences"],
    "retrieval_count": 0,
    "usefulness_score": 0.50,
    "pii_detected": false,
    "injection_risk_score": 0.02,
    "session_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
    "metadata": {
      "source_url": "https://example.com"
    },
    "created_at": "2024-01-15T10:30:45.123Z",
    "updated_at": "2024-01-15T10:30:45.123Z"
  },
  "meta": {
    "deduplication": {
      "is_duplicate": false,
      "similar_memories": []
    },
    "processing_time_ms": 145
  }
}
```

**Response: 409 Conflict (Exact Duplicate)**

```json
{
  "error": {
    "code": "DUPLICATE_CONTENT",
    "message": "A memory with identical content already exists",
    "existing_memory_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901"
  }
}
```

**Response: 202 Accepted (PII Detected)**

```json
{
  "data": {
    "id": "...",
    "status": "quarantined",
    "pii_detected": true
  },
  "meta": {
    "message": "Memory quarantined for review due to PII detection"
  }
}
```

---

### GET /v1/memories

**List memories for an agent**

**Required Permission:** `memory:read`

**Request:**

```http
GET /v1/memories?agent_id={uuid}&limit=50&cursor={cursor}
  &category=preference&status=active&tags=ui,preferences
  &created_after=2024-01-01T00:00:00Z
  &sort=created_at:desc
Authorization: Bearer {token}
```

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `agent_id` | UUID | Yes | Filter by agent |
| `limit` | integer | No | 1-100, default 20 |
| `cursor` | string | No | Pagination cursor |
| `category` | enum | No | Filter by category |
| `status` | enum | No | `active`, `archived`, `all`. Default: `active` |
| `visibility` | enum | No | Filter by visibility scope |
| `tags` | string | No | Comma-separated tags (AND logic) |
| `search` | string | No | Full-text search in content |
| `pinned_only` | boolean | No | Only return pinned memories |
| `created_after` | ISO8601 | No | Filter by creation date |
| `created_before` | ISO8601 | No | Filter by creation date |
| `min_confidence` | float | No | Minimum confidence score |
| `sort` | string | No | `created_at:desc`, `retrieval_count:desc`, `confidence:desc`. Default: `created_at:desc` |

**Response: 200 OK**

```json
{
  "data": [
    {
      "id": "a1b2c3d4-...",
      "agent_id": "550e8400-...",
      "content": "User prefers dark mode",
      "category": "preference",
      "confidence": 0.95,
      "status": "active",
      "tags": ["ui", "preferences"],
      "retrieval_count": 47,
      "usefulness_score": 0.82,
      "created_at": "2024-01-15T10:30:45.123Z",
      "last_retrieved_at": "2024-01-20T14:22:00.000Z"
    }
  ],
  "pagination": {
    "has_more": true,
    "next_cursor": "eyJpZCI6ImExYjJjM2Q0In0",
    "prev_cursor": null,
    "total_count": 1247
  }
}
```

---

### GET /v1/memories/{memory_id}

**Get a single memory**

**Required Permission:** `memory:read`

**Request:**

```http
GET /v1/memories/a1b2c3d4-e5f6-7890-abcd-ef1234567890
Authorization: Bearer {token}
```

**Response: 200 OK**

```json
{
  "data": {
    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "agent_id": "550e8400-...",
    "org_id": "123e4567-...",
    "content": "User prefers dark mode in all interfaces",
    "content_tokens": 8,
    "category": "preference",
    "subcategory": "visual",
    "confidence": 0.95,
    "source": "user_provided",
    "source_trace_id": null,
    "status": "active",
    "visibility": "agent",
    "pinned": false,
    "tags": ["ui", "preferences"],
    "retrieval_count": 47,
    "usefulness_score": 0.82,
    "positive_feedback_count": 12,
    "negative_feedback_count": 1,
    "pii_detected": false,
    "injection_risk_score": 0.02,
    "session_id": "7c9e6679-...",
    "superseded_by": null,
    "merged_into": null,
    "metadata": {},
    "created_at": "2024-01-15T10:30:45.123Z",
    "updated_at": "2024-01-15T10:30:45.123Z",
    "last_retrieved_at": "2024-01-20T14:22:00.000Z"
  }
}
```

**Response: 404 Not Found**

```json
{
  "error": {
    "code": "MEMORY_NOT_FOUND",
    "message": "Memory 'a1b2c3d4-...' not found"
  }
}
```

---

### PATCH /v1/memories/{memory_id}

**Update a memory**

Only updates provided fields. Partial updates only.

**Required Permission:** `memory:write`

**Request:**

```http
PATCH /v1/memories/a1b2c3d4-e5f6-7890-abcd-ef1234567890
Authorization: Bearer {token}
Content-Type: application/json

{
  "content": "User strongly prefers dark mode in all interfaces",
  "confidence": 0.99,
  "tags": ["ui", "preferences", "confirmed"],
  "pinned": true
}
```

**Updatable Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `content` | string | New content (triggers re-embedding) |
| `category` | enum | Change category |
| `confidence` | float | Update confidence score |
| `tags` | string[] | Replace tag list |
| `metadata` | object | Merge with existing metadata |
| `pinned` | boolean | Toggle pinned status |
| `visibility` | enum | Change visibility scope |

**Note:** Updating `content` triggers:

1. New embedding generation (async, ~100-500ms)
2. Near-duplicate check against existing memories
3. Conflict detection if near-duplicate found
4. Memory version record creation

**Response: 200 OK**

```json
{
  "data": {
    "id": "a1b2c3d4-...",
    "content": "User strongly prefers dark mode...",
    "confidence": 0.99,
    "tags": ["ui", "preferences", "confirmed"],
    "pinned": true,
    "updated_at": "2024-01-20T15:00:00.000Z"
  },
  "meta": {
    "reembedding_scheduled": true,
    "estimated_reembedding_ms": 200
  }
}
```

---

### DELETE /v1/memories/{memory_id}

**Delete a memory**

Soft deletes by default. Use `?permanent=true` for GDPR compliance flows (requires admin permission).

**Required Permission:** `memory:delete`

**Request:**

```http
DELETE /v1/memories/a1b2c3d4-e5f6-7890-abcd-ef1234567890
Authorization: Bearer {token}
```

**Response: 200 OK**

```json
{
  "data": {
    "id": "a1b2c3d4-...",
    "status": "deleted",
    "deleted_at": "2024-01-20T15:00:00.000Z"
  }
}
```

**Permanent Deletion:**

```http
DELETE /v1/memories/a1b2c3d4-...?permanent=true
X-MFA-Code: 123456
```

**Response: 200 OK**

```json
{
  "data": {
    "id": "a1b2c3d4-...",
    "permanently_deleted": true,
    "deletion_certificate_id": "cert_abc123",
    "deleted_at": "2024-01-20T15:00:00.000Z"
  }
}
```

---

### POST /v1/memories/search

**Semantic search over memories**

Searches memories using vector similarity. More powerful than the list endpoint's `search` parameter because it uses embeddings rather than full-text search.

**Required Permission:** `memory:read`

**Request:**

```http
POST /v1/memories/search
Authorization: Bearer {token}
Content-Type: application/json

{
  "agent_id": "550e8400-e29b-41d4-a716-446655440000",
  "query": "What are the user's UI preferences?",
  "limit": 10,
  "min_similarity": 0.7,
  "filters": {
    "category": ["preference", "behavioral"],
    "tags": ["ui"],
    "min_confidence": 0.6,
    "created_after": "2024-01-01T00:00:00Z"
  },
  "ranking": {
    "recency_weight": 0.25,
    "relevance_weight": 0.40,
    "usefulness_weight": 0.20,
    "confidence_weight": 0.10,
    "frequency_weight": 0.05
  }
}
```

**Request Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `agent_id` | UUID | Yes | Agent to search memories of |
| `query` | string | Yes | Natural language query |
| `limit` | integer | No | 1-50, default 10 |
| `min_similarity` | float | No | 0.0-1.0 similarity threshold |
| `filters` | object | No | Additional filters |
| `ranking` | object | No | Custom ranking weights (must sum to 1.0) |
| `session_id` | UUID | No | Include session-specific memories |
| `include_archived` | boolean | No | Include archived memories |

**Response: 200 OK**

```json
{
  "data": {
    "results": [
      {
        "memory": {
          "id": "a1b2c3d4-...",
          "content": "User prefers dark mode in all interfaces",
          "category": "preference",
          "confidence": 0.95,
          "created_at": "2024-01-15T10:30:45.123Z"
        },
        "scores": {
          "similarity": 0.94,
          "recency": 0.72,
          "usefulness": 0.82,
          "confidence": 0.95,
          "frequency": 0.47,
          "composite": 0.87
        },
        "rank": 1
      }
    ],
    "total_candidates_evaluated": 847,
    "search_time_ms": 42
  }
}
```

---

### POST /v1/memories/bulk

**Bulk create memories**

Creates up to 100 memories in a single request. Processed as individual memories with shared metadata.

**Required Permission:** `memory:write`

**Request:**

```http
POST /v1/memories/bulk
Authorization: Bearer {token}
Content-Type: application/json

{
  "agent_id": "550e8400-...",
  "memories": [
    {
      "content": "User prefers TypeScript over JavaScript",
      "category": "preference",
      "tags": ["programming"]
    },
    {
      "content": "User's primary database is PostgreSQL",
      "category": "factual",
      "tags": ["infrastructure"]
    }
  ],
  "options": {
    "skip_duplicates": true,
    "conflict_strategy": "newer_wins"
  }
}
```

**Response: 207 Multi-Status**

```json
{
  "data": {
    "created": 2,
    "skipped": 0,
    "failed": 0,
    "results": [
      {
        "index": 0,
        "status": "created",
        "memory_id": "a1b2c3d4-..."
      },
      {
        "index": 1,
        "status": "created",
        "memory_id": "b2c3d4e5-..."
      }
    ]
  }
}
```

---

### POST /v1/memories/{memory_id}/feedback

**Submit feedback on memory usefulness**

Used to improve memory ranking over time. Called after agent uses a memory and outcome is known.

**Required Permission:** `memory:write`

**Request:**

```http
POST /v1/memories/a1b2c3d4-.../feedback
Authorization: Bearer {token}
Content-Type: application/json

{
  "feedback": "positive",
  "session_id": "7c9e6679-...",
  "trace_id": "550e8400-...",
  "notes": "Memory helped agent answer question correctly"
}
```

**Request Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `feedback` | enum | Yes | `positive`, `negative`, `neutral` |
| `session_id` | UUID | No | Session where feedback applies |
| `trace_id` | UUID | No | Specific trace where memory was used |
| `notes` | string | No | Human notes about feedback |

**Response: 200 OK**

```json
{
  "data": {
    "memory_id": "a1b2c3d4-...",
    "feedback": "positive",
    "new_usefulness_score": 0.85,
    "total_positive_feedback": 13,
    "total_negative_feedback": 1
  }
}
```

---

## Sessions API

### POST /v1/sessions

**Create a new agent session**

**Required Permission:** `session:create`

**Request:**

```http
POST /v1/sessions
Authorization: Bearer {token}
Content-Type: application/json

{
  "agent_id": "550e8400-e29b-41d4-a716-446655440000",
  "metadata": {
    "environment": "production",
    "client_version": "1.2.3"
  },
  "tags": ["customer-support", "tier-1"]
}
```

**Response: 201 Created**

```json
{
  "data": {
    "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
    "agent_id": "550e8400-...",
    "org_id": "123e4567-...",
    "status": "active",
    "directive_version_id": "d4e5f6a7-...",
    "started_at": "2024-01-20T15:00:00.000Z",
    "last_heartbeat_at": "2024-01-20T15:00:00.000Z",
    "checkpoint_sequence": 0,
    "total_turns": 0,
    "tags": ["customer-support", "tier-1"],
    "metadata": {
      "environment": "production",
      "client_version": "1.2.3"
    }
  }
}
```

---

### GET /v1/sessions

**List sessions**

**Required Permission:** `session:read`

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `agent_id` | UUID | No | Filter by agent |
| `status` | enum | No | `active`, `suspended`, `completed`, `failed`, `all` |
| `started_after` | ISO8601 | No | Filter by start time |
| `started_before` | ISO8601 | No | Filter by start time |
| `tags` | string | No | Comma-separated tags |
| `limit` | integer | No | 1-100, default 20 |
| `cursor` | string | No | Pagination cursor |

**Response: 200 OK**

```json
{
  "data": [
    {
      "id": "7c9e6679-...",
      "agent_id": "550e8400-...",
      "status": "completed",
      "started_at": "2024-01-20T15:00:00.000Z",
      "completed_at": "2024-01-20T15:45:00.000Z",
      "total_turns": 24,
      "total_tokens_used": 45230,
      "total_memories_read": 87,
      "total_memories_written": 3,
      "error_count": 0
    }
  ],
  "pagination": {
    "has_more": false,
    "next_cursor": null,
    "total_count": 1
  }
}
```

---

### GET /v1/sessions/{session_id}

**Get session details**

**Required Permission:** `session:read`

**Response: 200 OK**

```json
{
  "data": {
    "id": "7c9e6679-...",
    "agent_id": "550e8400-...",
    "org_id": "123e4567-...",
    "directive_version_id": "d4e5f6a7-...",
    "status": "active",
    "started_at": "2024-01-20T15:00:00.000Z",
    "last_heartbeat_at": "2024-01-20T15:44:50.000Z",
    "checkpoint_sequence": 5,
    "last_checkpoint_at": "2024-01-20T15:40:00.000Z",
    "loop_suspected": false,
    "total_turns": 24,
    "total_tokens_used": 45230,
    "total_memories_read": 87,
    "total_memories_written": 3,
    "total_tool_calls": 12,
    "error_count": 0,
    "recovery_attempts": 0,
    "client_sdk_version": "1.2.3",
    "client_language": "python",
    "environment": "production",
    "tags": ["customer-support"],
    "metadata": {}
  }
}
```

---

### POST /v1/sessions/{session_id}/heartbeat

**Send session heartbeat**

Must be called every 10 seconds to keep session active. Called automatically by SDK.

**Required Permission:** `session:create`

**Request:**

```http
POST /v1/sessions/7c9e6679-.../heartbeat
Authorization: Bearer {token}
Content-Type: application/json

{
  "turn_count": 24,
  "tokens_used_delta": 1250
}
```

**Response: 200 OK**

```json
{
  "data": {
    "session_id": "7c9e6679-...",
    "status": "active",
    "next_heartbeat_required_by": "2024-01-20T15:45:30.000Z"
  }
}
```

**Response: 404 Not Found (Session Expired)**

```json
{
  "error": {
    "code": "SESSION_NOT_FOUND",
    "message": "Session has expired or been terminated"
  }
}
```

---

### POST /v1/sessions/{session_id}/checkpoint

**Create session checkpoint**

Saves current session state for crash recovery.

**Required Permission:** `session:create`

**Request:**

```http
POST /v1/sessions/7c9e6679-.../checkpoint
Authorization: Bearer {token}
Content-Type: application/json

{
  "state": {
    "conversation": [
      {"role": "user", "content": "Help me debug this"},
      {"role": "assistant", "content": "Sure, let me look..."}
    ],
    "pending_memories": [],
    "completed_tools": [
      {
        "tool": "read_file",
        "idempotency_key": "tool_abc123",
        "result": "success"
      }
    ],
    "plan_state": null,
    "variables": {
      "current_file": "main.py",
      "debug_mode": true
    }
  }
}
```

**Response: 201 Created**

```json
{
  "data": {
    "checkpoint_id": "cp_abc123",
    "session_id": "7c9e6679-...",
    "sequence_number": 6,
    "created_at": "2024-01-20T15:45:00.000Z",
    "state_size_bytes": 2048,
    "is_valid": true
  }
}
```

---

### POST /v1/sessions/{session_id}/resume

**Resume a suspended session**

**Required Permission:** `session:create`

**Request:**

```http
POST /v1/sessions/7c9e6679-.../resume
Authorization: Bearer {token}
Content-Type: application/json

{
  "checkpoint_sequence": null
}
```

**Response: 200 OK**

```json
{
  "data": {
    "session_id": "7c9e6679-...",
    "status": "active",
    "checkpoint": {
      "sequence_number": 5,
      "state": {
        "conversation": [...],
        "pending_memories": [],
        "completed_tools": [...],
        "variables": {}
      }
    },
    "ambiguities": [
      {
        "type": "tool_unknown_outcome",
        "tool": "write_file",
        "idempotency_key": "tool_xyz789",
        "message": "Tool was in-flight at crash time. Verify outcome before proceeding."
      }
    ],
    "resumed_at": "2024-01-20T16:00:00.000Z"
  }
}
```

---

### POST /v1/sessions/{session_id}/terminate

**Terminate a session**

**Required Permission:** `session:terminate`

**Request:**

```http
POST /v1/sessions/7c9e6679-.../terminate
Authorization: Bearer {token}
Content-Type: application/json

{
  "reason": "Task completed successfully",
  "status": "completed"
}
```

**Response: 200 OK**

```json
{
  "data": {
    "session_id": "7c9e6679-...",
    "final_status": "completed",
    "terminated_at": "2024-01-20T16:30:00.000Z",
    "summary": {
      "total_turns": 47,
      "total_tokens": 89420,
      "memories_created": 5,
      "memories_read": 142,
      "duration_seconds": 5400
    }
  }
}
```

---

### GET /v1/sessions/{session_id}/replay

**Get session replay data**

Returns events for session replay in the dashboard.

**Required Permission:** `session:read`

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `from_turn` | integer | Start from turn number |
| `to_turn` | integer | End at turn number |
| `event_types` | string | Filter event types (comma-separated) |
| `limit` | integer | Max events to return |
| `cursor` | string | Pagination cursor |

**Response: 200 OK**

```json
{
  "data": {
    "session_id": "7c9e6679-...",
    "events": [
      {
        "sequence_number": 1,
        "event_type": "inference_request",
        "timestamp": "2024-01-20T15:00:05.000Z",
        "data": {
          "messages": [...],
          "model": "gpt-4-turbo",
          "context_tokens": 2048
        }
      },
      {
        "sequence_number": 2,
        "event_type": "memory_read",
        "timestamp": "2024-01-20T15:00:05.042Z",
        "data": {
          "memory_ids": ["a1b2c3d4-..."],
          "query": "user preferences",
          "scores": [0.94]
        }
      },
      {
        "sequence_number": 3,
        "event_type": "inference_response",
        "timestamp": "2024-01-20T15:00:07.500Z",
        "data": {
          "completion_tokens": 342,
          "latency_ms": 2458
        }
      }
    ],
    "pagination": {
      "has_more": true,
      "next_cursor": "eyJzZXEiOjN9"
    }
  }
}
```

---

## Agents API

### POST /v1/agents

**Create an agent**

**Required Permission:** `agent:write`

**Request:**

```http
POST /v1/agents
Authorization: Bearer {token}
Content-Type: application/json

{
  "name": "Customer Support Agent",
  "description": "Handles tier-1 customer support inquiries",
  "slug": "customer-support",
  "config": {
    "memory_extraction_enabled": true,
    "drift_detection_enabled": true,
    "drift_sensitivity": 2.0,
    "context_budget_tokens": 4000,
    "max_memories_per_context": 20,
    "loop_detection_threshold": 5
  },
  "tags": ["production", "support"]
}
```

**Response: 201 Created**

```json
{
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "org_id": "123e4567-...",
    "name": "Customer Support Agent",
    "description": "Handles tier-1 customer support inquiries",
    "slug": "customer-support",
    "status": "active",
    "active_directive_version_id": null,
    "config": {
      "memory_extraction_enabled": true,
      "drift_detection_enabled": true,
      "drift_sensitivity": 2.0,
      "context_budget_tokens": 4000,
      "max_memories_per_context": 20,
      "loop_detection_threshold": 5
    },
    "total_sessions": 0,
    "total_memories": 0,
    "total_tokens_used": 0,
    "last_active_at": null,
    "tags": ["production", "support"],
    "created_at": "2024-01-20T15:00:00.000Z"
  }
}
```

---

### GET /v1/agents

**List agents**

**Required Permission:** `agent:read`

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `status` | enum | `active`, `paused`, `archived`, `all` |
| `tags` | string | Filter by tags |
| `search` | string | Search by name or description |
| `limit` | integer | 1-100, default 20 |
| `cursor` | string | Pagination cursor |

**Response: 200 OK**

```json
{
  "data": [
    {
      "id": "550e8400-...",
      "name": "Customer Support Agent",
      "slug": "customer-support",
      "status": "active",
      "total_sessions": 1247,
      "total_memories": 8903,
      "total_tokens_used": 45230000,
      "last_active_at": "2024-01-20T14:55:00.000Z",
      "tags": ["production", "support"],
      "created_at": "2024-01-01T00:00:00.000Z"
    }
  ],
  "pagination": {
    "has_more": false,
    "total_count": 1
  }
}
```

---

### GET /v1/agents/{agent_id}

**Get agent details**

**Required Permission:** `agent:read`

**Response: 200 OK**

```json
{
  "data": {
    "id": "550e8400-...",
    "org_id": "123e4567-...",
    "name": "Customer Support Agent",
    "description": "Handles tier-1 customer support inquiries",
    "slug": "customer-support",
    "status": "active",
    "active_directive_version_id": "d4e5f6a7-...",
    "config": {...},
    "total_sessions": 1247,
    "total_memories": 8903,
    "total_tokens_used": 45230000,
    "last_active_at": "2024-01-20T14:55:00.000Z",
    "tags": ["production", "support"],
    "metadata": {},
    "created_at": "2024-01-01T00:00:00.000Z",
    "updated_at": "2024-01-15T10:00:00.000Z"
  }
}
```

---

### PATCH /v1/agents/{agent_id}

**Update an agent**

**Required Permission:** `agent:write`

**Request:**

```http
PATCH /v1/agents/550e8400-...
Authorization: Bearer {token}
Content-Type: application/json

{
  "name": "Customer Support Agent v2",
  "config": {
    "context_budget_tokens": 6000
  },
  "tags": ["production", "support", "v2"]
}
```

**Response: 200 OK**

```json
{
  "data": {
    "id": "550e8400-...",
    "name": "Customer Support Agent v2",
    "config": {
      "memory_extraction_enabled": true,
      "drift_detection_enabled": true,
      "drift_sensitivity": 2.0,
      "context_budget_tokens": 6000,
      "max_memories_per_context": 20,
      "loop_detection_threshold": 5
    },
    "tags": ["production", "support", "v2"],
    "updated_at": "2024-01-20T16:00:00.000Z"
  }
}
```

---

### POST /v1/agents/{agent_id}/pause

**Pause an agent**

Prevents new sessions from starting. Existing sessions continue until natural completion.

**Required Permission:** `agent:write`

**Response: 200 OK**

```json
{
  "data": {
    "agent_id": "550e8400-...",
    "status": "paused",
    "active_sessions": 3,
    "message": "Agent paused. 3 active sessions will complete normally."
  }
}
```

---

### GET /v1/agents/{agent_id}/stats

**Get agent statistics**

**Required Permission:** `agent:read`

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `period` | enum | `24h`, `7d`, `30d`, `90d`, `all` |
| `granularity` | enum | `hour`, `day`, `week` |

**Response: 200 OK**

```json
{
  "data": {
    "agent_id": "550e8400-...",
    "period": "7d",
    "summary": {
      "total_sessions": 89,
      "total_tokens": 1240000,
      "total_memories_created": 234,
      "total_memories_retrieved": 4521,
      "avg_session_duration_seconds": 1247,
      "avg_turns_per_session": 18.4,
      "error_rate": 0.012,
      "avg_context_assembly_ms": 42
    },
    "timeseries": [
      {
        "timestamp": "2024-01-14T00:00:00.000Z",
        "sessions": 12,
        "tokens": 180000,
        "errors": 1
      }
    ],
    "top_memories": [
      {
        "memory_id": "a1b2c3d4-...",
        "content": "User prefers dark mode",
        "retrieval_count_in_period": 47
      }
    ]
  }
}
```

---

## Directives API

### POST /v1/directives

**Create a directive**

**Required Permission:** `directive:write`

**Request:**

```http
POST /v1/directives
Authorization: Bearer {token}
Content-Type: application/json

{
  "name": "Customer Support Directive",
  "description": "Instructions for handling tier-1 support",
  "initial_content": "You are a helpful customer support agent..."
}
```

**Response: 201 Created**

```json
{
  "data": {
    "id": "f7a8b9c0-...",
    "org_id": "123e4567-...",
    "name": "Customer Support Directive",
    "description": "Instructions for handling tier-1 support",
    "total_versions": 1,
    "active_version": {
      "id": "d4e5f6a7-...",
      "version_number": 1,
      "status": "draft",
      "content_tokens": 250,
      "created_at": "2024-01-20T15:00:00.000Z"
    },
    "created_at": "2024-01-20T15:00:00.000Z"
  }
}
```

---

### POST /v1/directives/{directive_id}/versions

**Create a new directive version**

**Required Permission:** `directive:write`

**Request:**

```http
POST /v1/directives/f7a8b9c0-.../versions
Authorization: Bearer {token}
Content-Type: application/json

{
  "content": "You are a helpful customer support agent for IBEX...",
  "parent_version_id": "d4e5f6a7-...",
  "change_summary": "Added escalation instructions",
  "breaking_changes": false
}
```

**Response: 201 Created**

```json
{
  "data": {
    "id": "e5f6a7b8-...",
    "directive_id": "f7a8b9c0-...",
    "version_number": 2,
    "parent_version_id": "d4e5f6a7-...",
    "status": "draft",
    "content_tokens": 312,
    "change_summary": "Added escalation instructions",
    "breaking_changes": false,
    "regression_test_status": "pending",
    "created_at": "2024-01-20T16:00:00.000Z"
  }
}
```

---

### POST /v1/directives/{directive_id}/versions/{version_id}/submit-review

**Submit directive version for review**

Triggers behavioral regression test suite.

**Required Permission:** `directive:write`

**Response: 200 OK**

```json
{
  "data": {
    "version_id": "e5f6a7b8-...",
    "status": "review",
    "regression_test_status": "running",
    "estimated_completion_seconds": 120,
    "scenarios_to_run": 47
  }
}
```

---

### POST /v1/directives/{directive_id}/versions/{version_id}/promote

**Promote directive version to active**

Requires: review approved, regression tests passed. Requires MFA for admin-level directives.

**Required Permission:** `directive:promote`

**Request:**

```http
POST /v1/directives/f7a8b9c0-.../versions/e5f6a7b8-.../promote
Authorization: Bearer {token}
X-MFA-Code: 123456
Content-Type: application/json

{
  "rollout_strategy": "immediate",
  "agent_ids": ["550e8400-..."]
}
```

**Rollout Strategies:**

| Strategy | Description |
|----------|-------------|
| `immediate` | All new sessions use new version immediately |
| `new_sessions_only` | Existing sessions complete with old version |
| `gradual` | 10% → 50% → 100% over time with monitoring |

**Response: 200 OK**

```json
{
  "data": {
    "version_id": "e5f6a7b8-...",
    "status": "active",
    "activated_at": "2024-01-20T17:00:00.000Z",
    "rollout": {
      "strategy": "immediate",
      "affected_agents": 1,
      "previous_version_id": "d4e5f6a7-..."
    }
  }
}
```

---

### POST /v1/directives/{directive_id}/versions/{version_id}/revoke

**Emergency revoke a directive version**

Immediately switches all active sessions to fallback. Requires 2-person approval in enterprise tier.

**Required Permission:** `directive:revoke`

**Request:**

```http
POST /v1/directives/f7a8b9c0-.../versions/e5f6a7b8-.../revoke
Authorization: Bearer {token}
X-MFA-Code: 123456
Content-Type: application/json

{
  "reason": "Security vulnerability discovered in instructions",
  "approver_id": "user_abc123"
}
```

**Response: 200 OK**

```json
{
  "data": {
    "version_id": "e5f6a7b8-...",
    "status": "revoked",
    "revoked_at": "2024-01-20T17:30:00.000Z",
    "affected_sessions": 47,
    "sessions_transitioned_to_fallback": 47
  }
}
```

---

### GET /v1/directives/{directive_id}/versions/{version_id}/diff

**Get diff between directive versions**

**Required Permission:** `directive:read`

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `compare_to` | UUID | Version to compare against. Default: parent |
| `format` | enum | `unified`, `split`. Default: `unified` |

**Response: 200 OK**

```json
{
  "data": {
    "version_a": {
      "id": "d4e5f6a7-...",
      "version_number": 1
    },
    "version_b": {
      "id": "e5f6a7b8-...",
      "version_number": 2
    },
    "diff": {
      "format": "unified",
      "content": "--- version_1\n+++ version_2\n@@ -15,6 +15,12 @@\n ...",
      "additions": 12,
      "deletions": 3,
      "token_delta": 62
    },
    "behavioral_comparison": {
      "test_scenarios_run": 47,
      "behavior_changed": 3,
      "behavior_unchanged": 44,
      "changes": [
        {
          "scenario": "Escalation request",
          "before": "Attempted to resolve independently",
          "after": "Correctly escalated to tier-2",
          "assessment": "improvement"
        }
      ]
    }
  }
}
```

---

## Analytics API

### GET /v1/analytics/overview

**Get organization analytics overview**

**Required Permission:** `trace:read`

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `period` | enum | `24h`, `7d`, `30d`, `90d` |
| `agent_ids` | string | Comma-separated agent IDs |

**Response: 200 OK**

```json
{
  "data": {
    "period": "7d",
    "summary": {
      "total_requests": 84721,
      "total_tokens": 124000000,
      "total_sessions": 1247,
      "total_memories_created": 3421,
      "avg_proxy_overhead_ms": 18,
      "avg_context_assembly_ms": 41,
      "p95_total_latency_ms": 2840,
      "error_rate": 0.008,
      "estimated_cost_usd": 124.50
    },
    "trends": {
      "requests_change_pct": 12.4,
      "tokens_change_pct": 8.7,
      "error_rate_change_pct": -2.1
    },
    "top_agents": [
      {
        "agent_id": "550e8400-...",
        "agent_name": "Customer Support",
        "request_count": 45231,
        "token_count": 67000000
      }
    ],
    "model_distribution": {
      "gpt-4-turbo": 0.65,
      "gpt-3.5-turbo": 0.25,
      "claude-3-opus": 0.10
    }
  }
}
```

---

### GET /v1/analytics/latency

**Get latency breakdown analytics**

**Required Permission:** `trace:read`

**Response: 200 OK**

```json
{
  "data": {
    "period": "24h",
    "latency_breakdown": {
      "proxy_overhead": {
        "p50": 12,
        "p95": 28,
        "p99": 67
      },
      "context_assembly": {
        "p50": 35,
        "p95": 52,
        "p99": 89
      },
      "auth_validation": {
        "p50": 0.8,
        "p95": 2.1,
        "p99": 45
      },
      "rate_limit_check": {
        "p50": 1.2,
        "p95": 3.4,
        "p99": 8.7
      },
      "provider_latency": {
        "p50": 1240,
        "p95": 3200,
        "p99": 5800
      }
    },
    "slow_requests": [
      {
        "trace_id": "...",
        "total_latency_ms": 8920,
        "provider_latency_ms": 7800,
        "context_assembly_ms": 890,
        "timestamp": "2024-01-20T14:22:00.000Z"
      }
    ]
  }
}
```

---

### GET /v1/analytics/memory-performance

**Get memory system performance analytics**

**Required Permission:** `trace:read`

**Response: 200 OK**

```json
{
  "data": {
    "period": "7d",
    "retrieval_stats": {
      "total_retrievals": 427819,
      "avg_memories_per_request": 5.1,
      "avg_retrieval_latency_ms": 38,
      "cache_hit_rate": 0.67,
      "empty_result_rate": 0.04
    },
    "quality_stats": {
      "avg_relevance_score": 0.84,
      "positive_feedback_rate": 0.89,
      "negative_feedback_rate": 0.04
    },
    "top_retrieved_memories": [
      {
        "memory_id": "a1b2c3d4-...",
        "content_preview": "User prefers dark mode...",
        "retrieval_count": 1247,
        "avg_score": 0.91
      }
    ],
    "memory_growth": {
      "created_this_period": 3421,
      "archived_this_period": 124,
      "conflict_resolutions": 47,
      "deduplication_saves": 891
    }
  }
}
```

---

## Tokens API

### POST /v1/tokens

**Create an API token**

**Required Permission:** `admin:token_create`

**Request:**

```http
POST /v1/tokens
Authorization: Bearer {token}
X-MFA-Code: 123456
Content-Type: application/json

{
  "name": "Production SDK Token",
  "description": "Token for production agent deployment",
  "type": "org_token",
  "agent_id": "550e8400-...",
  "permissions": ["memory:read", "memory:write", "session:create"],
  "expires_at": null,
  "allowed_ips": ["10.0.0.0/8"]
}
```

**Permissions Reference:**

```text
memory:read              -- Read and search memories
memory:write             -- Create and update memories
memory:delete            -- Delete memories
directive:read           -- Read directives
directive:write          -- Create and update directives
directive:promote        -- Promote directives to active
directive:revoke         -- Emergency revoke directives
session:create           -- Create and manage sessions
session:read             -- Read session data
session:terminate        -- Terminate sessions
trace:read               -- Read inference traces
trace:export             -- Export trace data
agent:read               -- Read agent data
agent:write              -- Create and update agents
admin:token_create       -- Create API tokens
admin:user_manage        -- Manage organization users
admin:billing            -- Access billing data
admin:audit_log          -- Read audit log
```

**Response: 201 Created**

```json
{
  "data": {
    "id": "tok_abc123",
    "name": "Production SDK Token",
    "type": "org_token",
    "prefix": "ibex_org_7f3k",
    "token": "ibex_org_7f3k2m9x...",
    "permissions": ["memory:read", "memory:write", "session:create"],
    "expires_at": null,
    "allowed_ips": ["10.0.0.0/8"],
    "created_at": "2024-01-20T15:00:00.000Z"
  },
  "meta": {
    "warning": "Store this token securely. It will not be shown again."
  }
}
```

---

### DELETE /v1/tokens/{token_id}

**Revoke a token**

**Required Permission:** `admin:token_create`

**Request:**

```http
DELETE /v1/tokens/tok_abc123
Authorization: Bearer {token}
Content-Type: application/json

{
  "reason": "Token compromised in security incident"
}
```

**Response: 200 OK**

```json
{
  "data": {
    "token_id": "tok_abc123",
    "revoked": true,
    "revoked_at": "2024-01-20T17:00:00.000Z",
    "propagation_estimated_ms": 100
  }
}
```

---

## Organizations API

### GET /v1/organizations/me

**Get current organization**

**Required Permission:** Any valid token

**Response: 200 OK**

```json
{
  "data": {
    "id": "123e4567-...",
    "name": "Acme Corporation",
    "slug": "acme-corp",
    "tier": "pro",
    "status": "active",
    "created_at": "2024-01-01T00:00:00.000Z",
    "usage": {
      "current_period": {
        "tokens_used": 45230000,
        "token_quota": 100000000,
        "token_usage_pct": 45.2,
        "memory_count": 89030,
        "memory_quota": 1000000,
        "memory_usage_pct": 8.9
      },
      "period": "2024-01",
      "resets_at": "2024-02-01T00:00:00.000Z"
    },
    "limits": {
      "monthly_tokens": 100000000,
      "max_memories": 1000000,
      "max_agents": 50,
      "requests_per_minute": 1000
    }
  }
}
```

---

### GET /v1/organizations/me/usage

**Get detailed usage data**

**Required Permission:** `admin:billing`

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `period` | string | `YYYY-MM` format. Default: current month |
| `breakdown` | enum | `agent`, `day`, `event_type` |

**Response: 200 OK**

```json
{
  "data": {
    "period": "2024-01",
    "total": {
      "tokens": 45230000,
      "memory_writes": 3421,
      "memory_reads": 427819,
      "sessions": 1247,
      "api_calls": 84721
    },
    "by_agent": [
      {
        "agent_id": "550e8400-...",
        "agent_name": "Customer Support",
        "tokens": 23000000,
        "memory_writes": 1847,
        "sessions": 891
      }
    ],
    "daily_breakdown": [
      {
        "date": "2024-01-15",
        "tokens": 1847000,
        "requests": 2841
      }
    ],
    "estimated_cost_usd": 45.23
  }
}
```

---

## Webhook API

### POST /v1/webhooks

**Register a webhook endpoint**

**Required Permission:** `admin:token_create`

**Request:**

```http
POST /v1/webhooks
Authorization: Bearer {token}
Content-Type: application/json

{
  "url": "https://your-server.com/ibex-webhooks",
  "events": [
    "memory.created",
    "memory.conflict_detected",
    "session.failed",
    "drift.detected",
    "directive.promoted",
    "quota.threshold_reached"
  ],
  "secret": "your_webhook_secret_here",
  "agent_ids": ["550e8400-..."]
}
```

**Available Events:**

```text
memory.created              -- New memory written
memory.conflict_detected    -- Memory conflict requires review
memory.deleted              -- Memory deleted
session.started             -- New session started
session.completed           -- Session completed normally
session.failed              -- Session failed with error
session.loop_detected       -- Agent loop detected
session.suspended           -- Session heartbeat lost
drift.detected              -- Behavioral drift detected
drift.resolved              -- Drift alert resolved
directive.submitted_review  -- Directive awaiting review
directive.promoted          -- Directive made active
directive.revoked           -- Directive emergency revoked
quota.80_percent            -- 80% of monthly quota used
quota.95_percent            -- 95% of monthly quota used
quota.exceeded              -- Monthly quota exhausted
```

**Response: 201 Created**

```json
{
  "data": {
    "id": "wh_abc123",
    "url": "https://your-server.com/ibex-webhooks",
    "events": ["memory.created", "drift.detected"],
    "status": "active",
    "created_at": "2024-01-20T15:00:00.000Z"
  }
}
```

---

### Webhook Payload Format

All webhooks use this envelope:

```json
{
  "id": "evt_abc123",
  "type": "drift.detected",
  "api_version": "v1",
  "created_at": "2024-01-20T15:30:00.000Z",
  "org_id": "123e4567-...",
  "data": {
    "alert_id": "da_xyz789",
    "agent_id": "550e8400-...",
    "severity": "high",
    "alerts": [
      {
        "feature": "tool_call_rate",
        "baseline_value": 0.4,
        "current_value": 0.87,
        "z_score": 3.8
      }
    ]
  }
}
```

---

## LLM Proxy API

### POST /proxy/v1/chat/completions

**Proxy OpenAI-compatible chat completion**

Drop-in replacement for OpenAI's chat completions endpoint. Context and memory injection happen transparently.

**Service route (direct proxy):** `POST /v1/chat/completions` — same handler; `/proxy` is the external gateway path prefix.

**Phase 1 behavior:** Authenticated requests with valid JSON are parsed; response is **501 Not Implemented** with `PROVIDER_NOT_CONFIGURED` until Phase 2 provider forwarding. Malformed JSON returns **400** with `INVALID_JSON`.

**Request:**

```http
POST /proxy/v1/chat/completions
Authorization: Bearer {token}
Content-Type: application/json
X-IBEX-Agent-ID: 550e8400-e29b-41d4-a716-446655440000
X-IBEX-Session-ID: 7c9e6679-7425-40de-944b-e07fc1f90ae7

{
  "model": "gpt-4-turbo",
  "messages": [
    {
      "role": "user",
      "content": "What UI settings does the user prefer?"
    }
  ],
  "temperature": 0.7,
  "max_tokens": 1000,
  "stream": false
}
```

**IBEX-Specific Headers:**

| Header | Required | Description |
|--------|----------|-------------|
| `X-IBEX-Agent-ID` | Yes | Agent making the request |
| `X-IBEX-Session-ID` | No | Current session (creates new if absent) |
| `X-IBEX-Skip-Memory` | No | `true` to disable memory injection |
| `X-IBEX-Skip-Extraction` | No | `true` to disable memory extraction |
| `X-IBEX-Directive-Override` | No | Override directive version ID |

**Response: 200 OK** (non-streaming)

```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1705753845,
  "model": "gpt-4-turbo",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Based on the available context, the user..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 2048,
    "completion_tokens": 342,
    "total_tokens": 2390
  },
  "ibex": {
    "trace_id": "550e8400-...",
    "session_id": "7c9e6679-...",
    "memories_injected": 5,
    "context_tokens_used": 1247,
    "context_assembly_ms": 38,
    "proxy_overhead_ms": 15
  }
}
```

**Response: 200 OK** (streaming, `stream: true`)

```text
data: {"id":"chatcmpl-abc123","choices":[{"delta":{"content":"Based"},...}]}

data: {"id":"chatcmpl-abc123","choices":[{"delta":{"content":" on"},...}]}

data: [DONE]
```

**Response: 429 Too Many Requests**

```json
{
  "error": {
    "message": "Rate limit exceeded",
    "type": "rate_limit_error",
    "code": "RATE_LIMIT_EXCEEDED"
  }
}
```

Response headers:

```http
Retry-After: 45
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1705753900
```

---

### POST /proxy/v1/messages

**Proxy Anthropic-compatible messages**

Same behavior as OpenAI proxy but with Anthropic's message format.

```http
POST /proxy/v1/messages
Authorization: Bearer {token}
X-IBEX-Agent-ID: 550e8400-...
anthropic-version: 2023-06-01
Content-Type: application/json

{
  "model": "claude-3-opus-20240229",
  "max_tokens": 1024,
  "messages": [
    {
      "role": "user",
      "content": "What are the user's preferences?"
    }
  ]
}
```

---

## gRPC API

Internal gRPC contracts live under [packages/proto/proto/ibex/](../packages/proto/proto/ibex/). Generated stubs are produced locally (`make proto-gen`) and are not committed to git — see [ADR-0004](adr/ADR-0004-protobuf-and-codegen-policy.md).

### Auth Service (`ibex.auth.v1`)

The Auth service exposes `AuthService.ValidateToken` for internal consumers (e.g. the LLM proxy). Source of truth: [packages/proto/proto/ibex/auth/v1/auth.proto](../packages/proto/proto/ibex/auth/v1/auth.proto). Contract policy: [ADR-0006](adr/ADR-0006-auth-proto-contract.md).

- **ValidateToken** — no caller metadata required (proxy hot path)
  - **Request:** `access_token` — full `Authorization: Bearer ...` value
  - **Response (success):** `org_id`, `permissions` (int64 bitmap), optional `agent_id`, `user_id`, `token_id`, `expires_at`
  - **Errors:** `Unauthenticated` for invalid/revoked/expired tokens

**Permission bitmap:** [ADR-0009](adr/ADR-0009-permission-bitmap.md), `packages/permissions`. Admin bits: `TokenCreate` (36), `TokenRevoke` (37). Phase 2 proxy minimum: `ProxyChatCompletion`.

**Management RPCs** (internal; milestone 1.1.4):

| RPC | Caller | Notes |
| --- | --- | --- |
| `CreateToken` | `authorization: Bearer` + `TokenCreate` | `plaintext` returned once only |
| `RevokeToken` | Bearer + `TokenRevoke` or own token | Cross-org → `NotFound` |
| `ListTokens` | Bearer + `TokenCreate` | Metadata only; no hash/plaintext |

Additional errors: `InvalidArgument`, `PermissionDenied`, `NotFound` per [ADR-0006](adr/ADR-0006-auth-proto-contract.md).

**Permission bitmap:** 64-bit `permissions` field per [ADR-0009](adr/ADR-0009-permission-bitmap.md). Go source of truth: `packages/permissions`. Key admin bits for token management:

| Bit | Constant | Required for |
| --- | --- | --- |
| 36 | `TokenCreate` | `CreateToken`, `ListTokens` (caller bearer in metadata) |
| 37 | `TokenRevoke` | Revoking another user's token in the same org |

**Phase 2 proxy minimum:** `permissions.ProxyChatCompletion` = `MemoryRead | SessionCreate | SessionRead`.

Management RPCs (`CreateToken`, `RevokeToken`, `ListTokens`) are documented in milestone 1.1.4; callers must send gRPC metadata `authorization: Bearer <pat>` except for `ValidateToken`.

### Context Assembly (`ibex.context.v1`)

The Context Assembly Engine exposes a gRPC API consumed internally by the proxy. Not exposed publicly.

### Proto Definition (context)

```protobuf
syntax = "proto3";
package ibex.context.v1;

service ContextAssemblyService {
  // Assemble context for an inference call
  rpc AssembleContext(AssembleContextRequest)
      returns (AssembleContextResponse);

  // Retrieve memories without full assembly
  rpc SearchMemories(SearchMemoriesRequest)
      returns (SearchMemoriesResponse);

  // Update memory usefulness after outcome known
  rpc RecordMemoryFeedback(RecordMemoryFeedbackRequest)
      returns (RecordMemoryFeedbackResponse);
}

message AssembleContextRequest {
  string agent_id = 1;
  string org_id = 2;
  string session_id = 3;
  string query = 4;
  string model = 5;
  string directive_version_id = 6;
  int32 available_tokens = 7;
  repeated Message recent_messages = 8;
  AssemblyOptions options = 9;
}

message AssemblyOptions {
  bool skip_cold_memories = 1;
  bool skip_hot_memories = 2;
  float recency_weight = 3;
  float relevance_weight = 4;
  float usefulness_weight = 5;
  float confidence_weight = 6;
  int32 max_memories = 7;
}

message AssembleContextResponse {
  string assembled_context = 1;
  int32 tokens_used = 2;
  int32 memories_included = 3;
  repeated MemoryUsed memories_used = 4;
  int32 directive_tokens = 5;
  int32 history_tokens = 6;
  int32 memory_tokens = 7;
  AssemblyMetrics metrics = 8;
}

message AssemblyMetrics {
  int32 budget_calculation_ms = 1;
  int32 directive_load_ms = 2;
  int32 hot_memory_retrieval_ms = 3;
  int32 cold_memory_retrieval_ms = 4;
  int32 ranking_ms = 5;
  int32 packing_ms = 6;
  int32 formatting_ms = 7;
  int32 total_ms = 8;
  int32 candidates_evaluated = 9;
}

message MemoryUsed {
  string memory_id = 1;
  float composite_score = 2;
  float relevance_score = 3;
  float recency_score = 4;
  float usefulness_score = 5;
  int32 rank = 6;
  string category = 7;
}

message Message {
  string role = 1;
  string content = 2;
}

message SearchMemoriesRequest {
  string agent_id = 1;
  string org_id = 2;
  string query = 3;
  int32 limit = 4;
  float min_similarity = 5;
  repeated string categories = 6;
  repeated string tags = 7;
  string session_id = 8;
}

message SearchMemoriesResponse {
  repeated Memory memories = 1;
  int32 total_candidates = 2;
  int32 search_time_ms = 3;
}

message Memory {
  string id = 1;
  string content = 2;
  string category = 3;
  float confidence = 4;
  float composite_score = 5;
  int32 retrieval_count = 6;
  string created_at = 7;
}

message RecordMemoryFeedbackRequest {
  repeated string memory_ids = 1;
  string session_id = 2;
  string trace_id = 3;
  string org_id = 4;
  string feedback = 5;  // "positive", "negative", "neutral"
}

message RecordMemoryFeedbackResponse {
  bool success = 1;
  repeated MemoryScoreUpdate updates = 2;
}

message MemoryScoreUpdate {
  string memory_id = 1;
  float previous_score = 2;
  float new_score = 3;
}
```

---

## 📌 API Versioning Policy

### Version Lifecycle

```text
v1 (current):  Fully supported
v2 (future):   Announced when breaking changes needed
```

### Breaking vs Non-Breaking Changes

**Non-breaking (no version bump):**

- Adding new optional fields to requests
- Adding new fields to responses
- Adding new endpoints
- Adding new enum values
- Relaxing validation constraints

**Breaking (requires version bump):**

- Removing or renaming fields
- Changing field types
- Changing response structures
- Adding required fields
- Changing authentication behavior
- Changing pagination format

### Deprecation Process

```text
Month 0:   Breaking change identified
Month 1:   New version launched, deprecation notice sent
           Old version: Deprecation header added to responses
Month 1-12: Both versions supported
Month 12:  Old version receives no new features
Month 13:  Old version returns 410 Gone with migration guide
```

**Deprecation Headers:**

```http
X-IBEX-Deprecation: true
X-IBEX-Deprecation-Date: 2025-01-15
X-IBEX-Sunset-Date: 2025-06-01
X-IBEX-Successor: https://api.ibexharness.com/v2/
Link: <https://docs.ibexharness.com/migration/v1-to-v2>; rel="deprecation"
```

---

## 🧪 Testing Your Integration

### Test Mode

Add header to any request to run in test mode:

```http
X-IBEX-Test-Mode: true
```

**Test mode:**

- Requests don't count toward quotas
- No actual LLM calls (uses mock responses)
- Data created in test namespace (auto-deleted after 24h)
- Clearly marked in responses: `"test_mode": true`

### Sandbox Environment

```text
Base URL: https://sandbox.ibexharness.com
```

- Isolated from production data
- Free to use for development
- Seeded with sample data
- Reset weekly (Sundays 00:00 UTC)

### API Playground

Interactive documentation with live API testing:

```text
https://docs.ibexharness.com/playground
```

Features:

- Try any endpoint with your real credentials
- View request/response in formatted JSON
- Generate SDK code snippets
- Export as curl, Python, TypeScript, Go
