# services/

Deployable runtime components for IBEX Harness.

| Directory | Role | Status |
| --- | --- | --- |
| `proxy/` | Go — LLM proxy (latency-critical) | **Shipped (Phase 1):** auth middleware, agent verification, rate limiting, request parsing, health/metrics |
| `auth/` | Go — authentication and token validation | **Shipped (Phase 1):** gRPC `ValidateToken` / `ValidateAgent`, Argon2id PAT verify, Postgres stores |
| `api/` | Python FastAPI — management plane | Planned (Phase 3) |
| `memory/` | Python FastAPI — memory CRUD and vector search | Planned (Phase 3) |
| `context/` | Python gRPC — context assembly | Planned (Phase 3) |
| `embedder/` | Python FastAPI — embeddings | Planned (Phase 3) |
| `worker/` | Python Celery — async jobs | Planned (Phase 3) |
| `dashboard/` | Next.js — operator UI | Planned (Phase 3) |

The public marketing/docs/benchmarks site lives in `web/` (Phase 1.5), not under `services/`.

Scaffold layout and future service boundaries: [web/engineering/FILE_STRUCTURE.md](../web/engineering/FILE_STRUCTURE.md).
