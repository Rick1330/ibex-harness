# services/

Deployable runtime components for IBEX Harness (anything that runs as a process).

Directory names and phase assignments below are the **current planning baseline** from the redesigned roadmap (Phases 2.5–5). Exact layouts may change during implementation when live constraints and research say so — see [Changing this inventory](#changing-this-inventory).

The public marketing/docs/benchmarks site lives in `web/` (Phase 1.5+), not under `services/`. Current shipped status: [roadmap current state](https://ibexharness.com/roadmap/current-state). Scaffold guidance: [web/engineering/FILE_STRUCTURE.md](../web/engineering/FILE_STRUCTURE.md).

---

## Shipped

| Directory | Role | Status |
| --- | --- | --- |
| `proxy/` | Go — LLM proxy (latency-critical): auth middleware, agent verification, rate limiting, provider forwarding (OpenAI + Anthropic), auth cache, directives + injection, sessions, ClickHouse traces, idempotency, health/metrics | **Shipped (Phase 2)** — continues in 2.5+ (capability registry, self-hosted adapters, response pipeline, context client, multi-provider routing) |
| `auth/` | Go — authentication and token validation: gRPC `ValidateToken` / `ValidateAgent` / PAT lifecycle, Argon2id, Postgres stores, revoke pub/sub | **Shipped (Phase 2)** — extends in Phase 4 (e.g. provider-credential RPCs) |

---

## Planned (redesigned roadmap)

| Directory | Role | Preferred phase | Notes |
| --- | --- | --- | --- |
| `embedder/` | Python FastAPI — pluggable embedding backends (TEI / hosted API / CPU fallback), content-hash cache | **2.5** | Deployment-time embedding profile; dimensionality is not interchangeable without migration |
| `tokenizer-service/` | Python FastAPI — accurate token counts via Hugging Face `tokenizers` (optional dual-path with in-process Go/CGo in the proxy) | **2.5** | Situational: may be deferred if proxy-side counting alone proves sufficient for early budgets |
| `mcp-memory/` | Python — MCP server exposing audited memory tools (search / write / feedback), OAuth via existing Auth gRPC | **2.5 skeleton → 3.5 tools** | Separate lifecycle from proxy/API/context; early skeleton may land under this name before full tools |
| `memory/` | Python FastAPI (+ related clients) — memory schema/ORM, write pipeline, vector store, semantic search, hot cache | **3** | Core memory substrate; not the place for extraction workers |
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
