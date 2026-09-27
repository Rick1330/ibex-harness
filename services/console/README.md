# IBEX Console (`@ibex/console`)

`services/console` is the **canonical operator application**. `services/dashboard` is a temporary compatibility shell and must not become a second Track D product. The Console presentation layer preserves the supplied dashboard mock’s navigation, typography, themes, responsive layout, and domain route structure; the data boundary remains server-owned.

## Local commands

From the repository root:

```bash
pnpm install --frozen-lockfile --ignore-scripts
pnpm --filter @ibex/console dev
pnpm --filter @ibex/console test
pnpm --filter @ibex/console lint
pnpm --filter @ibex/console typecheck
pnpm --filter @ibex/console build
```

Open `/dashboard` for the presentation shell. Preview/fixture mode is explicitly opt-in and is disabled in production.

## Surface status

| Surface | Status | Evidence and boundary |
| --- | --- | --- |
| Shell, navigation, themes, responsive layout, cards, charts, tables, dialogs, and route presentation | **Implemented presentation** | Transplanted from the supplied mock; see `src/app`, `src/components`, and `src/lib`. |
| Server-only DAL/BFF transport, request-time `no-store`, and opt-in live mode | **Mounted-but-provisional** | The server boundary may call only the configured `IBEX_OPERATOR_API_ORIGIN`; browser code never receives upstream credentials or tenant authority. |
| D1 context/overview and platform/event transport | **Mounted-but-provisional** | API ownership and local tests exist; hosted AuthService/session, origin, deployment, reconnect, and two-tenant evidence remain open. |
| D2 Explore trace metadata list/detail | **Mounted-but-provisional** | `CONSOLE_DATA_MODE=live` plus `CONSOLE_READ_ONLY=1` reads the tenant-scoped metadata-only contract. Unavailable sections are explicit; no content or provenance is fabricated. |
| Login, signup, TOTP enrollment, token issuance, invites, and authenticated mutations | **Deferred** | AuthService owns these flows; this shell does not expose fake credentials or demo passwords. |
| Sessions, memories, directives, incidents, drift, analytics, billing, settings, raw trace content, replay, export, and operator actions | **Preview/deferred** | Fixture presentation may exist, but owning APIs, permissions, redaction, audit, and acceptance evidence are not claimed. |

## Configuration boundary

| Variable | Meaning |
| --- | --- |
| `CONSOLE_DATA_MODE` | `preview` or opt-in `live` data mode; not authentication |
| `CONSOLE_READ_ONLY` | Must remain `1` for the current D2 live slice |
| `IBEX_OPERATOR_API_ORIGIN` | Server-only, approved upstream origin for operator reads |
| `CONSOLE_PREVIEW` / `NEXT_PUBLIC_CONSOLE_PREVIEW` | Presentation preview flags; never tenant authority or credential controls |

Legacy `OPERATOR_WEB_*` names are migration aliases only. Never put a bearer token, AuthService secret, organization ID, or upstream URL authority in browser-exposed configuration.

## Security and readiness

The current shell has no login route or demo credentials. AuthService-backed sessions, secure-cookie policy, MFA, CSRF-protected mutations, exact credentialed CORS, deployment origin, and rollback evidence remain required before production promotion. The D2 live seam forwards only the configured access-session cookie, enforces server-side tenant scope, validates responses with runtime schemas, and uses `Cache-Control: no-store`.

Browser preferences may use `localStorage`, a non-auth layout cookie, or `sessionStorage`; none is a credential or tenant-authority store. Untrusted memory, Markdown, HTML, links, prompts, and tool content must remain inert or sanitized.

## Verification and handoff

Tests cover route inventory, response contracts, classification boundaries, and the metadata-only D2 state. Any expansion beyond the current slice must add an owning API contract, tenant-negative tests, redaction/hostile-content tests, accessibility checks, performance evidence, and a rollback plan before changing this README’s status.
