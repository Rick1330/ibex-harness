# ADR-0018: Graceful shutdown contract (Phase 1)

- **Status:** Accepted
- **Date:** 2026-06-07
- **Authors:** IBEX Harness team

## Context

Auth and proxy services previously used ad-hoc `signal.Notify` handlers with a hardcoded 10-second drain timeout. Kubernetes rolling updates send SIGTERM; without configurable, ordered shutdown, in-flight HTTP and gRPC work can be dropped during deploys.

M1.3.1 will register OTel provider shutdown on the same coordinator. Phase 2 long-lived streams may need longer drain windows.

## Decision

### 1) Shared `packages/shutdown.Coordinator`

Both `services/auth` and `services/proxy` use `shutdown.Coordinator`:

- `Register(fn)` — handlers run in registration order on shutdown signal
- `Wait()` — blocks until SIGTERM or SIGINT, runs handlers with a shared drain context

Ad-hoc signal handling in `main.go` is forbidden ([29-ibex-packages.mdc](../.cursor/rules/29-ibex-packages.mdc)).

### 2) Signal semantics

| Signal | Behavior |
| --- | --- |
| **SIGTERM** | Graceful drain within `IBEX_SHUTDOWN_TIMEOUT` (default `30s`) |
| **SIGINT** | Immediate shutdown — zero drain timeout (development convenience) |

### 3) Environment variable

`IBEX_SHUTDOWN_TIMEOUT` — Go duration string (e.g. `30s`, `60s`). Default: `30s`.

Canonical name per [24-config-management.mdc](../.cursor/rules/24-config-management.mdc). Documented in service `.env.example` files and [ENVIRONMENT_VARIABLES.md](../ENVIRONMENT_VARIABLES.md).

### 4) Shutdown sequences

**Proxy:**

```text
SIGTERM/SIGINT → http.Server.Shutdown → auth gRPC conn Close → Redis Close → exit
```

**Auth:**

```text
SIGTERM/SIGINT → gRPC GracefulStop (with Stop fallback on timeout) → http.Server.Shutdown → db.Close → exit
```

gRPC `GracefulStop` runs in a goroutine; if the drain context expires, `grpc.Server.Stop()` forces termination.

### 5) Exit codes

| Outcome | Exit code |
| --- | --- |
| All handlers completed within drain window | `0` |
| Drain timeout exceeded | `1` |

Handler errors are logged but do not change exit code unless the drain deadline is exceeded.

### 6) Deferred

- OTel `Providers.Shutdown` registration (M1.3.1)
- ClickHouse writer flush (Phase 2)
- WebSocket / hijacked connection drain (Phase 2 — note in risks)

## Consequences

### Positive

- Single coordinator for all Phase 1 services and future shutdown hooks
- K8s-friendly SIGTERM drain with configurable timeout
- Auth DB closed after HTTP/gRPC drain (not at process start via `defer`)

### Negative

- SIGINT immediate shutdown may drop in-flight requests in local dev (acceptable trade-off)

## References

- [Milestone 1.2.7](../roadmap/phase-1-core-platform/milestones/1.2.7-graceful-shutdown.md)
- [Milestone 1.3.1](../roadmap/phase-1-core-platform/milestones/1.3.1-otel-tracer-provider-init.md)
- [29-ibex-packages.mdc](../.cursor/rules/29-ibex-packages.mdc)
