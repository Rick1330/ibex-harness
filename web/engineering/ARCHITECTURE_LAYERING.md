# Architecture layering and interface ports

Companion to [ARCHITECTURE.md](./ARCHITECTURE.md) (system topology) and
[ADR-0020](/docs/adr/0020-shared-package-boundaries) (config/apierror package
boundaries). This note covers **where Go interfaces live**.

## Dependency direction

```text
Handler / middleware (transport)
        ↓
Service / use-case
        ↓
Repository / store / adapter
        ↓
Infrastructure (DB, Redis, gRPC clients)
```

Lower layers must not import higher layers. `packages/**` must not import
`services/**` (enforced by depguard `packages-no-services`).

## Consumer-owned ports (preferred for service-local churn)

High-churn contracts used by a single service’s transport layer should be
defined **next to the consumer**, not next to the adapter.

Examples:

| Port | Owner | Adapters |
| --- | --- | --- |
| `http.TokenValidator`, `http.AgentVerifier` | `services/proxy/internal/http` | `services/proxy/internal/auth` (gRPC + cache wrap) |
| `http/trace.TraceWriter` | `services/proxy/internal/http/trace` | ClickHouse writer |
| `tokenAPI`, `validateForOrger` (unexported) | `services/auth/internal/grpc` | `service.TokenService`, `service.AgentService` |

Middleware and handlers depend on the local port. Wiring injects concrete
adapters that satisfy the port structurally.

Do **not** relocate `packages/authcache.Validator` — that remains the shared
cache upstream contract used inside the auth cache decorator.

## Shared package interfaces (intentional exception)

Some `packages/*` types are **multi-consumer public APIs** (like `io.Reader`):
the interface and the primary implementation ship together because more than
one service depends on the same contract.

| Package | Interface | Why keep with implementation |
| --- | --- | --- |
| `packages/session` | `Store` | Proxy + future workers share session lifecycle |
| `packages/idempotency` | `Store` | Proxy HTTP + other writers share Redis key shape |
| `packages/directive` | `Resolver` | Proxy hot path + loaders share directive resolution |
| `packages/ratelimit` | `Limiter` | Proxy + auth-adjacent limiters share sliding-window contract |

These are **not** “producer-owned by accident.” Treat changes as shared API
changes: update all consumers, keep key formats and RLS/org_id rules stable.

Narrow shared packages (`packages/config`, `packages/apierror`) remain under
ADR-0020 import rules.

## Related

- [CODING_STANDARDS.md](./CODING_STANDARDS.md) — interface design (“define at consumer”)
- [AGENTS.md](../../AGENTS.md) — agent workflow and architecture layering invariants
- [GOLANGCI_POLICY.md](./GOLANGCI_POLICY.md) — depguard / MF-001 proxy Postgres exception ([ADR-0039](/docs/adr/0039-proxy-postgres-session-directive))
