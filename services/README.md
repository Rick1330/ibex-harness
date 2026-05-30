# services/

Deployable runtime components for IBEX Harness.

Planned services (see [docs/FILE_STRUCTURE.md](../docs/FILE_STRUCTURE.md)):

| Directory | Role |
| --- | --- |
| `proxy/` | Go — LLM proxy (latency-critical) |
| `auth/` | Go — authentication and token validation |
| `api/` | Python FastAPI — management plane |
| `memory/` | Python FastAPI — memory CRUD and vector search |
| `context/` | Python gRPC — context assembly |
| `embedder/` | Python FastAPI — embeddings |
| `worker/` | Python Celery — async jobs |
| `dashboard/` | Next.js — operator UI |

**Available now:**

- `auth/` - Go skeleton with `/health`, `/ready`, and `/metrics`
- `proxy/` - Go skeleton with `/health`, `/ready`, and `/metrics`

Other services remain planned and should be bootstrapped via [docs/FILE_STRUCTURE.md](../docs/FILE_STRUCTURE.md) scaffolds.
