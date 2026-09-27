# IBEX Console Service (`@ibex/console`)

This directory contains the IBEX operator web **service**. Its JavaScript manifest (`package.json`) exists to build and run the service; the architectural boundary is the service, not a reusable library package. Its presentation layer is a **faithful transplant of the supplied dashboard mock** at `/home/ubuntu/dash-board-mock/dash-board-mock`: the same Geist/mono/serif typography, neutral surface tokens, sidebar/header chrome, responsive spacing, cards, charts, tables, dialogs, navigation, auth atmosphere, onboarding composition, and domain route structure are kept directly rather than re-created as a simplified shell.

## Local use

From the repository root:

```bash
pnpm --filter @ibex/console dev
pnpm --filter @ibex/console typecheck
pnpm --filter @ibex/console test
pnpm --filter @ibex/console lint
pnpm --filter @ibex/console build
```

For the visual dashboard shell, start the service and open `/dashboard` directly:

```bash
pnpm --filter @ibex/console dev
```

The presentation shell intentionally has no login route or demo credentials. AuthService-backed sessions, tenant authority, MFA, and authenticated mutations remain deferred. A guarded live mode supports the D2 metadata-only Explore list/detail slice through the server-only DAL; it is not a substitute for hosted AuthService or two-tenant acceptance evidence.

## Surface classification

| Surface                                                                                                               | Status                        | Boundary                                                                                                                                                                                  |
| --------------------------------------------------------------------------------------------------------------------- | ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Transplanted sidebar, header, theme system, responsive layout, cards, charts, tables, dialogs, and route presentation | **Implemented presentation**  | Directly adapted from the supplied mock; only import, root-layout, route, and safety boundaries changed.                                                                                  |
| Overview and mock domain fixtures                                                                                     | **Preview-only**              | The mock fixture modules remain presentation fixtures. They are reachable only through an explicit preview build/runtime flag; production has no fixture adapter.                         |
| Login, signup, and TOTP credential flows                                                                               | **Removed/deferred**          | No credential entry, demo password, token minting, or MFA enrollment is exposed in this shell. AuthService owns the future implementation.                                               |
| Dashboard shell                                                                                                       | **Presentation-only**         | The shell is directly reachable for inspection; it has no tenant authority and authenticated mutations remain disabled.                                                             |
| Explore metadata list/detail                                                                                           | **Mounted-but-provisional**  | With `CONSOLE_DATA_MODE=live`, `CONSOLE_READ_ONLY=1`, and server-only `IBEX_OPERATOR_API_ORIGIN`, the live pages read the tenant-scoped D2 metadata contract. No raw content or unavailable sections are synthesized. |
| Sessions, memories, directives, incidents, drift, analytics, billing, settings data                                  | **Deferred/live integration** | Mock routes remain preview-only; richer reads, authorization, mutations, evidence contracts, and upstream fetches require separate owning APIs and acceptance gates. |

## Preview configuration migration

The internal preview flags use the Console names. Migrate local configuration as follows; these flags are not production authentication or tenant-authority controls.

| Legacy variable | Console variable |
| --- | --- |
| `OPERATOR_WEB_DATA_MODE` | `CONSOLE_DATA_MODE` |
| `OPERATOR_WEB_PREVIEW` | `CONSOLE_PREVIEW` |
| `NEXT_PUBLIC_OPERATOR_WEB_PREVIEW` | `NEXT_PUBLIC_CONSOLE_PREVIEW` |

Preview remains enabled only when the server-side mode and preview flags are set together with the public presentation flag, and it is always disabled when `NODE_ENV=production`.

## Security posture

There is no browser-side arbitrary upstream fetch, bearer credential, client-supplied organization authority, fake login, or browser secret. The auth context is credential-free and exists only to preserve future step-up integration seams; it never loads, manufactures, or stores a session. Token issuance, bearer-curl generation, and TOTP enrollment are not exposed.

The copied mock code is intentionally classified as presentation-only. Theme/sidebar/onboarding preferences may use browser `localStorage`, the sidebar uses a non-auth layout cookie, and the drift banner uses `sessionStorage`; none is a credential or tenant-authority store. Authenticated API reads beyond the D2 metadata slice, mutations, token issuance, invites, and richer trace traffic require validated tenant-scoped contracts before production integration. The D2 live seam is opt-in and fail-closed; it forwards only the configured access-session cookie and uses request-time `no-store` responses.

## Verification and handoff

The supplied mock source is intentionally kept recognizable in `src/app`, `src/components`, and `src/lib`; unused failed custom shell components were removed by replacing the old source tree. Before live integration, connect AuthService and tenant-scoped API contracts at the server boundary, then replace fixture-only domain reads with validated, authorized responses while retaining the same presentation states.
