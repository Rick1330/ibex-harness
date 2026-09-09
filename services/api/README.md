# IBEX Management API (m4.A.1 skeleton)

Python FastAPI management-plane service. This milestone ships plumbing only:
auth via gRPC `ValidateToken`, org-scoped Postgres sessions (`app.current_org_id`),
IBEX error envelope, request-ID correlation, health/ready, and an authenticated
tenant ping that proves RLS + `WHERE org_id` double-enforcement.

Resource CRUD (orgs/users/agents/tokens/credentials) lands in **4.A.2+**.

## Endpoints

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| GET | `/health` | no | Liveness |
| GET | `/ready` | no | Auth gRPC + Postgres `SELECT 1` |
| GET | `/metrics` | no | Prometheus |
| GET | `/v1/tenant/ping` | Bearer | Sets GUC + `SELECT id FROM ibex_core.organizations WHERE id = :org_id` |
| GET | `/openapi.json` / `/docs` | no | FastAPI defaults |

## Environment

| Variable | Required | Description |
|----------|----------|-------------|
| `IBEX_API_DATABASE_URL` | for ready/tenant | `postgresql+asyncpg://...` |
| `IBEX_AUTH_GRPC_ADDR` / `IBEX_API_AUTH_GRPC_ADDR` | yes (default `127.0.0.1:8081`) | Auth ValidateToken target |
| `IBEX_API_AUTH_TIMEOUT_MS` | no | default 50 |
| `IBEX_API_HOST` / `IBEX_API_PORT` | no | bind (default port **8010**) |
| `IBEX_API_DOCS_BASE_URL` | no | error `docs_url` prefix |

## Cursor pagination (forward pointer — not implemented in 4.A.1)

List endpoints in 4.A.2+ should follow `web/engineering/API_DOCUMENTATION.md`:

```json
{
  "data": [],
  "pagination": {
    "has_more": true,
    "next_cursor": "...",
    "prev_cursor": "...",
    "total_count": 0
  }
}
```

No `CursorPage` helper ships in this milestone.

## Local run

```bash
cd services/api
uv sync --extra dev
uvicorn app.main:app --host 127.0.0.1 --port 8010
```
