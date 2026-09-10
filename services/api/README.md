# IBEX Management API (m4.A.1 + m4.A.2 + m4.A.3)

Python FastAPI management-plane service.

- **4.A.1:** auth via gRPC `ValidateToken`, org-scoped Postgres sessions (`app.current_org_id`),
  IBEX error envelope, request-ID correlation, health/ready, tenant ping.
- **4.A.2:** organization lifecycle (get/patch/suspend/delete), user CRUD with invites,
  last-owner protection, org-suspend Redis propagation (`event_type=org_suspend`), and
  thin async org-deletion job status (ADR-0073).
- **4.A.3:** agent CRUD + lifecycle (activate/pause/archive), soft-delete when
  `total_sessions == 0`, `default_provider` / `default_model`, and
  `active_directive_version_id` derived from directives.

## Endpoints

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| GET | `/health` | no | Liveness |
| GET | `/ready` | no | Auth gRPC + Postgres `SELECT 1` |
| GET | `/metrics` | no | Prometheus |
| GET | `/v1/tenant/ping` | Bearer | Sets GUC + org SELECT |
| GET | `/v1/organizations/{id}` | Bearer | Path org must match token org (else 404) |
| PATCH | `/v1/organizations/{id}` | owner/admin + `OrgSettingsWrite` | name, billing_email, settings |
| POST | `/v1/organizations/{id}/suspend` | owner + `OrgSettingsWrite` | Sets `suspended`; publishes `org_suspend` |
| DELETE | `/v1/organizations/{id}` | owner + `OrgSettingsWrite` | 202 + enqueue then cancel; 503 if broker unset/fails |
| GET | `/v1/organizations/{id}/deletion-jobs/{job_id}` | owner + `OrgSettingsWrite` | Thin job status |
| GET | `/v1/users` | Bearer | Cursor page, org-scoped |
| POST | `/v1/users` | owner/admin + `UserManage` | Invite; returns `invite_token` once |
| GET | `/v1/users/{id}` | Bearer | 404 cross-tenant / missing |
| PATCH | `/v1/users/{id}` | owner/admin + `UserManage` | role/name; only owner may set `role=owner`; last owner → 409 |
| DELETE | `/v1/users/{id}` | owner/admin + `UserManage` | Soft-delete; revoke user PATs (fail closed) |
| GET | `/v1/agents` | Bearer | Cursor page; filters `status`, `tags`, `search` |
| POST | `/v1/agents` | owner/admin + `OrgSettingsWrite` | Create; slug unique per org → 409 |
| GET | `/v1/agents/{id}` | Bearer | 404 cross-tenant / missing |
| PATCH | `/v1/agents/{id}` | owner/admin + `OrgSettingsWrite` | Slug immutable; soft provider/model |
| DELETE | `/v1/agents/{id}` | owner/admin + `OrgSettingsWrite` | Soft-delete; 409 if `total_sessions > 0` |
| POST | `/v1/agents/{id}/activate` | owner/admin + `OrgSettingsWrite` | From paused/archived/suspended |
| POST | `/v1/agents/{id}/pause` | owner/admin + `OrgSettingsWrite` | From active; proxy → `AGENT_SUSPENDED` |
| POST | `/v1/agents/{id}/archive` | owner/admin + `OrgSettingsWrite` | From non-archived |
| GET | `/v1/organizations/{id}/providers` | owner/admin + `OrgSettingsWrite` | List provider credential metadata |
| POST | `/v1/organizations/{id}/providers` | owner/admin + `OrgSettingsWrite` | Upsert credential (validate then Auth seal) |
| DELETE | `/v1/organizations/{id}/providers/{name}` | owner/admin + `OrgSettingsWrite` | Delete credential |
| GET | `/v1/organizations/{id}/rate-limits` | Bearer (path org) | Effective RPM + live org counter |
| PATCH | `/v1/organizations/{id}/rate-limits` | owner/admin + `OrgSettingsWrite` | Upsert/clear org/agent RPM; pub/sub invalidate |
| GET | `/openapi.json` / `/docs` | no | FastAPI defaults |

## Environment

| Variable | Required | Description |
|----------|----------|-------------|
| `IBEX_API_DATABASE_URL` | for ready/tenant | `postgresql+asyncpg://...` |
| `IBEX_AUTH_GRPC_ADDR` / `IBEX_API_AUTH_GRPC_ADDR` | yes (default `127.0.0.1:8081`) | Auth ValidateToken/RevokeToken target |
| `IBEX_API_AUTH_TIMEOUT_MS` | no | default 50 |
| `IBEX_API_REDIS_URL` | for suspend + rate-limit pub/sub | Redis for `org_suspend` and `ratelimit_config_updates:{org_id}`; optional for live RPM counters |
| `IBEX_API_RATE_LIMIT_DEFAULT_RPM` | no | Platform default org/agent RPM when no override row (default **60**) |
| `IBEX_API_CELERY_BROKER_URL` | for org DELETE | Required for delete; missing/fail → 503, org not cancelled |
| `IBEX_API_HOST` / `IBEX_API_PORT` | no | bind (default port **8010**) |
| `IBEX_API_DOCS_BASE_URL` | no | error `docs_url` prefix |

## Cursor pagination

List endpoints return:

```json
{
  "data": [],
  "pagination": {
    "has_more": true,
    "next_cursor": "...",
    "prev_cursor": null,
    "total_count": null
  }
}
```

## Authz model (ADR-0073)

Both apply:

1. `users.role` (`owner` / `admin` / `member` / `viewer`)
2. Token permission bitmap (ADR-0009): owner/admin → Admin, member → AgentDefault, viewer → ReadOnly

Cross-tenant path IDs return **404** (not 403) to avoid existence leaks.

## Local run

```bash
cd services/api
uv sync --extra dev
uvicorn app.main:app --host 127.0.0.1 --port 8010
```
