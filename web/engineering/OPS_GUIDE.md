# Operations Guide

Deployment and runtime operations for IBEX Harness Go services (Phase 1: `auth`, `proxy`).

## Health endpoints

Contract: [ADR-0022](adr/ADR-0022-health-check-contract.md).

| Endpoint | Probe type | Checks external deps | On failure |
| --- | --- | --- | --- |
| `GET /health` | Liveness | No | Kubernetes restarts the pod |
| `GET /ready` | Readiness | Yes (critical deps) | Pod removed from Service endpoints |

### Response schema

```json
{
  "status": "ok",
  "checks": {
    "postgres": { "status": "ok", "latency_ms": 2 }
  }
}
```

- `status`: `ok` | `degraded` | `unhealthy`
- Readiness returns HTTP **503** when `status` is `unhealthy`
- `degraded` (advisory check failed) returns HTTP **200** — not used in Phase 1

### Service checks (Phase 1)

| Service | Critical checks |
| --- | --- |
| `auth` | `postgres` (`SELECT 1`), `grpc` (TCP to gRPC port) |
| `proxy` | `auth_grpc` (ValidateToken probe), `redis` (`PING`) |

## Kubernetes probes

Recommended configuration for auth and proxy Deployments:

```yaml
ports:
  - name: http
    containerPort: 8080   # auth: 8081 per IBEX_PORT

livenessProbe:
  httpGet:
    path: /health
    port: http
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /ready
    port: http
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 2
  successThreshold: 1
```

Notes:

- Do not point liveness at `/ready` — dependency blips would restart pods unnecessarily
- Readiness **503** stops traffic; liveness failure triggers restart
- Per-check timeout is 500ms; overall `/ready` budget is 750ms — keep `timeoutSeconds: 2` on probes

## Local verification

```bash
curl -s http://localhost:8081/health | jq .
curl -s http://localhost:8081/ready | jq .
curl -s http://localhost:8080/ready | jq .
make dev-smoke
```

## Related docs

- [MONITORING.md](MONITORING.md) — metrics and observability
- [runbooks/RUNBOOKS.md](runbooks/RUNBOOKS.md) — incident response
- [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md) — configuration registry
