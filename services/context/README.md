# IBEX Context assembly service

Python context-assembly library and gRPC service for Phase 3.5. The current implementation covers budget calculation, parallel directive/hot/cold retrieval, scoring, bounded packing, safe formatting, and degradation. It is suitable for **loopback or a trusted network boundary only** until caller authentication is implemented.

> **Security warning:** the current gRPC server has no authentication interceptor. On a non-loopback bind it trusts request `org_id` and `agent_id` values. Do not expose it directly to an untrusted network or treat a configured network address as production-safe. Authenticated caller identity is deferred to 3.5.D.1.

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
| `IBEX_CONTEXT_GRPC_ADDR` | Bind address; keep loopback/trusted-only until auth interceptor exists |
| `IBEX_MEMORY_HTTP_URL` / `IBEX_MEMORY_API_TOKEN` | Memory service origin and server-side token |
| Redis directive settings | Directive lookup and hot-cache branch |

`retrieval_wall_ms = min(timeout_ms, deadline_ms)`. Branches degrade independently; a timeout must not silently cross tenant boundaries or invent memory content.

## Local run

```bash
# from repository root
bash infra/scripts/context-proto-gen.sh
bash infra/scripts/context-uv-sync.sh
PYTHONPATH=packages/proto/gen/python services/context/.venv/bin/python -m app
```

Keep `IBEX_CONTEXT_GRPC_ADDR=127.0.0.1:<port>` for local use. If a trusted sidecar boundary is unavoidable, document the network policy and do not claim caller authentication.

## Catalog freshness and tests

```bash
go run ./packages/provider/scripts/export_capabilities -o services/context/app/data/model_capabilities.v1.json
go run ./packages/provider/scripts/export_capabilities -check services/context/app/data/model_capabilities.v1.json
cd services/context && .venv/bin/pytest -q
```
