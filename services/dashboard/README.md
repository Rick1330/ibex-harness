# IBEX Operator UI (`services/dashboard`)

Minimal **static SPA** for Milestone **4.P.0** (runtime topology / environment contract).

## Scope

- Connection-state shell: `connected` / `reconnecting` / `degraded` / `drained` / `live` / `historical` / `unauthenticated`
- Cookie session against `services/api` (`credentials: "include"`)
- Operator-event SSE with `Last-Event-ID` resume
- **No secrets in deep links** — PAT only in a password field, cleared after login

Product dashboard content is **Track D** (out of scope). Full identity lifecycle is **4.P.1**.

## Local

```bash
pnpm --filter dashboard build
pnpm --filter dashboard dev   # http://localhost:3100 → serves dist/
```

Point the UI at the API (`http://127.0.0.1:8010` by default). Set `IBEX_ALLOWED_ORIGINS=http://localhost:3100` on the API.

## Deploy

Cloudflare Pages project **`ibex-harness-operator`** via `.github/workflows/operator-deploy.yml`.
Independent from docs (`ibex-harness-docs`). See [ADR-0078](../../web/content/docs/adr/0078-operator-runtime-topology.mdx).
