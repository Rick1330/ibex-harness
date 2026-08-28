# services/

Deployable runtime components for IBEX Harness (anything that runs as a process).

Directory names and phase assignments below are the **current planning baseline** from the redesigned roadmap (Phases 2.5–5). Exact layouts may change during implementation when live constraints and research say so — see [Changing this inventory](#changing-this-inventory).

The public marketing/docs/benchmarks site lives in `web/` (Phase 1.5+), not under `services/`. Current shipped status: [roadmap current state](https://ibexharness.com/roadmap/current-state). Scaffold guidance: [web/engineering/FILE_STRUCTURE.md](../web/engineering/FILE_STRUCTURE.md).

---

## Shipped

| Directory | Role | Status |
| --- | --- | --- |
| `proxy/` | Go — LLM proxy (latency-critical): auth middleware, agent verification, rate limiting, provider forwarding (OpenAI + Anthropic + self-hosted), auth cache, directives + injection, sessions, ClickHouse traces, idempotency, health/metrics | **Shipped (Phase 2 + 2.5)** |
| `auth/` | Go — authentication and token validation: gRPC `ValidateToken` / `ValidateAgent` / PAT lifecycle, Argon2id, Postgres stores, revoke pub/sub | **Shipped (Phase 2)** — extends in Phase 4 (e.g. provider-credential RPCs) |
| `embedder/` | Python FastAPI — embedding contract + backends (stub / TEI / hosted profiles), `/health`/`/ready` | **Shipped (Phase 2.5 / ADR-0046)** |
| `mcp-memory/` | Python — MCP resource server: Streamable HTTP, Auth gRPC fail-closed boundary, stub `search_memory`/`write_memory`, `mcp_tool_calls` audit | **Partial (2.5.G6.M1 / ADR-0050)** — real tool bodies in 3.5 |
| `memory/` | Python FastAPI — memory substrate: probes, scoring v2, VectorStore/PgVectorStore, embedder HTTP client, full write pipeline (`POST /v1/memories`: PII → dedup → conflict → persist → cache/index, multi-label `labels[]`) | **In progress (Phase 3)** — Tracks A–B + C complete; Track D read path next |

---

## Planned (redesigned roadmap)

| Directory | Role | Preferred phase | Notes |
| --- | --- | --- | --- |
| `tokenizer-service/` | Python FastAPI — accurate token counts via Hugging Face `tokenizers` (optional dual-path with in-process Go/CGo in the proxy) | **2.5** | Situational: may be deferred if proxy-side counting alone proves sufficient for early budgets |
| `worker/` | Python Celery (+ Redis) — extraction, embedding jobs, maintenance, later fingerprint/drift/regression tasks | **3.5** (intelligence jobs continue in **4.5**) | Preferred starting worker stack; alternatives (e.g. Temporal) only with evidence |
| `context/` | Python gRPC — context assembly (budget, retrieve, score, pack, format) with degradation contract | **3.5** | Hot-path dependency of the proxy via `packages/contextclient` |
| `api/` | Python FastAPI — management plane CRUD (orgs, users, agents, tokens, provider credentials, rate-limit config, …) | **4** | Operator/control plane; not the LLM proxy |
| `dashboard/` | Next.js — operator UI (agents, memories, traces, drift, directives, analytics, cost governance) | **4** | Separate from the public `web/` site |

Intelligence (fingerprinting, drift, directive regression) primarily extends `worker/`, `api/`, and `dashboard/` rather than introducing a separate “intelligence” process by default. Advanced retrieval (Phase 5) primarily extends `memory/` / `context/` / `mcp-memory/` rather than a new search service by default.

---

## Changing this inventory

The service list is **open to change** as the product and constraints evolve. Adding, removing, renaming, merging, or splitting services (or moving work between services and packages) is allowed when there is **strong evidence** — for example measured latency/cost, tenancy or security needs, deploy topology, or a clearer ownership boundary after reading the live code.

Changes should not be casual renames or speculative scaffolding. Prefer:

1. **Evidence** — what failed or what was measured, and why the current boundary is wrong
2. **Reasoning** — tradeoffs vs keeping or extending an existing service
3. **An ADR** — record the decision under `web/content/docs/adr/` and update this README + roadmap milestones that reference the old name
4. **Roadmap alignment** — update the relevant phase index/tracks so planning docs stay honest

Situational examples that may justify a change later: folding `tokenizer-service/` into another Python service; renaming the MCP surface; introducing a dedicated regression runner process if Celery proves the wrong fit; or keeping embedding inference as an external TEI sidecar only (with a thinner IBEX client). Those remain options — they are not commitments until evidence and an ADR say so.
