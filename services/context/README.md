# IBEX Context assembly service

Python context-assembly library and gRPC service for Phase 3.5. The current implementation covers budget calculation, parallel directive/hot/cold retrieval, scoring, bounded packing, safe formatting, and degradation. Every RPC now requires a caller service token ([ADR-0096](../../engineering/adr/0096-context-grpc-caller-authentication.md)). The service is still a plaintext, loopback-only host process: it has no Dockerfile, compose service, Helm template, or publish job, and it is not a deployment profile.

## Caller authentication (ADR-0096)

| Control | Behaviour |
| --- | --- |
| Caller token | Every RPC requires exactly one `x-ibex-context-service-token` metadata entry matching `IBEX_CONTEXT_GRPC_SERVICE_TOKEN` (`hmac.compare_digest` after a length check). Missing, duplicate, or mismatched → `UNAUTHENTICATED` with a constant message. Enforced by the registered handler wrapper and by every servicer method. |
| Principal | `principal_context` is required: `authority == "AuthService"`, canonical `org_id`/`agent_id` UUIDs, a bounded `principal_id`, `issued_at` within ±30 s, and a non-stale `expires_at`. Otherwise → `UNAUTHENTICATED`. |
| Selector binding | Request `org_id`/`agent_id` remain selectors only and must equal the principal; a mismatch is `PERMISSION_DENIED` before any Redis or memory call. |
| Derived authority | The directive key and the memory-hit tenant check use the principal, never the caller-supplied selectors. |
| Memory hits | Every hit from the memory service must carry the principal's `org_id` and `agent_id`. One foreign hit fails that retrieval branch with `memory_tenant_mismatch`, logged by `memory_id` only; nothing from the branch is packed. |
| Startup | The server refuses to start without a token (32–512 characters of `[A-Za-z0-9_-]`), refuses a token equal to `IBEX_CONTEXT_MEMORY_API_TOKEN`, and refuses any bind that does not resolve exclusively to loopback. |
| Port sharing | `grpc.so_reuseport` is disabled, so a same-UID process cannot share the listening port and capture the token. |

`SearchMemories` and `RecordMemoryFeedback` authenticate first: without a token they return `UNAUTHENTICATED`, and with a valid token they still return `UNIMPLEMENTED` (ADR-0038).

**Claim boundary.** This closes **unauthenticated reachability**. It is **not** per-user authentication: the service token is a shared secret and `PrincipalContext` is unsigned, so **a token holder can still assert any principal**. Tenant isolation remains a proxy-side property. There is no TLS, no principal signing, and no per-user validation at this boundary, and token rotation is a coordinated restart of the proxy and the context server with no overlap window.

## Current components

- `app/budget.py` — model-capability catalog, token budget and character/rune estimate (not exact tokenizer counts).
- `app/retrieval.py` — three-branch fail-open retrieval: directive Redis plus hot/cold memory HTTP.
- `app/packer.py` / `app/scoring.py` — bounded DP knapsack with greedy fallback and interim similarity/confidence scoring.
- `app/formatter.py` — deterministic ordering and escaped nonce-delimited memory serialization.
- `app/assemble.py` — retrieve → budget → score → pack → format (`L0–L2`).
- `app/server.py` — gRPC `AssembleContext`; `SearchMemories` and `RecordMemoryFeedback` intentionally return `UNIMPLEMENTED`.

## Runtime settings

| Setting | Meaning |
| --- | --- |
| `IBEX_CONTEXT_TIMEOUT` | Overall retrieval budget; default 45 ms |
| `IBEX_CONTEXT_DEADLINE_MS` | gRPC deadline; default 40 ms |
| `IBEX_CONTEXT_GRPC_SERVICE_TOKEN` | Shared caller token required on every RPC; 32–512 characters of `[A-Za-z0-9_-]`; secret, never logged |
| `IBEX_CONTEXT_GRPC_ADDR` | Bind address; must resolve exclusively to loopback or the server refuses to start |
| `IBEX_CONTEXT_MEMORY_BASE_URL` / `IBEX_CONTEXT_MEMORY_API_TOKEN` | Memory service origin and server-side token (aliases `MEMORY_BASE_URL` / `MEMORY_API_TOKEN`) |
| Redis directive settings | Directive lookup and hot-cache branch |

`retrieval_wall_ms = min(timeout_ms, deadline_ms)`. Branches degrade independently; a timeout must not silently cross tenant boundaries or invent memory content.

## Local run

```bash
# from repository root
bash infra/scripts/context-proto-gen.sh
bash infra/scripts/context-uv-sync.sh

# Shared caller token for both sides; it must differ from the memory token.
export IBEX_CONTEXT_GRPC_SERVICE_TOKEN="$(openssl rand -hex 32)"

# Memory service origin plus its own bearer (required by the server runtime).
export IBEX_CONTEXT_MEMORY_BASE_URL=http://127.0.0.1:8005
export IBEX_CONTEXT_MEMORY_API_TOKEN="<memory-service-token>"

PYTHONPATH=packages/proto/gen/python \
IBEX_CONTEXT_GRPC_ADDR=127.0.0.1:9092 \
  services/context/.venv/bin/python -m app
```

Run the proxy with the same token plus `IBEX_CONTEXT_ENABLED=true` and `IBEX_CONTEXT_GRPC_TARGET=127.0.0.1:9092`; the proxy requires the token when context is enabled. Keep `IBEX_CONTEXT_GRPC_ADDR=127.0.0.1:<port>`: the server itself refuses any non-loopback bind, and the token is plaintext, so a networked deployment needs TLS before it can be considered.

## Catalog freshness and tests

```bash
go run ./packages/provider/scripts/export_capabilities -o services/context/app/data/model_capabilities.v1.json
go run ./packages/provider/scripts/export_capabilities -check services/context/app/data/model_capabilities.v1.json
cd services/context && .venv/bin/pytest -q
```
