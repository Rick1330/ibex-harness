# services/

Deployable runtime components for IBEX Harness.

| Directory | Role | Status |
| --- | --- | --- |
| `proxy/` | Go — LLM proxy (latency-critical) | **Shipped (Phase 2):** auth middleware, agent verification, rate limiting, mock/live provider forwarding, auth cache, directives + injection, sessions, ClickHouse traces, idempotency, health/metrics |
| `auth/` | Go — authentication and token validation | **Shipped (Phase 2):** gRPC `ValidateToken` / `ValidateAgent` / PAT lifecycle, Argon2id verify, Postgres stores, revoke pub/sub |
| `api/` | Python FastAPI — management plane | Planned (Phase 3) |
| `memory/` | Python FastAPI — memory CRUD and vector search | Planned (Phase 3) |
| `context/` | Python gRPC — context assembly | Planned (Phase 3) |
| `embedder/` | Python FastAPI — embeddings | Planned (Phase 3) |
| `worker/` | Python Celery — async jobs | Planned (Phase 3) |
| `dashboard/` | Next.js — operator UI | Planned (Phase 3) |

The public marketing/docs/benchmarks site lives in `web/` (Phase 1.5+), not under `services/`. Current shipped status: [roadmap current state](https://ibexharness.com/roadmap/current-state).

Scaffold layout and future service boundaries: [web/engineering/FILE_STRUCTURE.md](../web/engineering/FILE_STRUCTURE.md).
