# IBEX Operator UI compatibility shell (`services/dashboard`)

This package is the **temporary 4.P.0 static compatibility shell**. It preserves the verified connection-state, credentialed API fetch, CSRF/login-body, and operator-event SSE parser behavior while the canonical authenticated product is migrated to `services/console`. It is not the Track D product and must not be expanded into a second production-intended dashboard.

## Scope and status

- **mounted-but-provisional:** connection states (`connected`, `reconnecting`, `degraded`, `drained`, `live`, `historical`, `unauthenticated`), credentialed API fetch, and `Last-Event-ID` SSE parsing/reconnect behavior.
- **Not implemented here:** the operator product routes, server-only DAL/BFF, authoritative context/overview/health/events composition, generated OpenAPI client, runtime DTO validation, and Track D domain surfaces.
- **Security boundary:** do not place PATs, sessions, CSRF secrets, provider keys, or raw tenant data in local or session storage. Treat all event and content payloads as untrusted.

## Local verification

The package currently exposes these scripts:

```bash
pnpm --filter dashboard build
pnpm --filter dashboard test
pnpm --filter dashboard dev   # serves the built dist/ on the package's local port
```

The shell's API origin and cookie/CORS/CSRF behavior must be supplied by a verified local API configuration. This README does not assert a staging or production hostname, deployment workflow, Cloudflare project, ingress, or public runtime.

## Migration and retirement

Use this shell only as a compatibility fallback while `services/console` is built and promoted. Retire it only after the canonical artifact has a parity matrix, four-role/two-tenant contract/browser/a11y/visual/hostile-content/cache/SSE/performance evidence, a rollback window, and an approved removal record for shell references.
