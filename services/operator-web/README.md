# `@ibex/operator-web`

This package is the IBEX operator surface. Its presentation layer is a **faithful transplant of the supplied dashboard mock** at `/home/ubuntu/dash-board-mock/dash-board-mock`: the same Geist/mono/serif typography, neutral surface tokens, sidebar/header chrome, responsive spacing, cards, charts, tables, dialogs, navigation, auth atmosphere, onboarding composition, and domain route structure are kept directly rather than re-created as a simplified shell.

## Local use

From the repository root:

```bash
pnpm --filter @ibex/operator-web dev
pnpm --filter @ibex/operator-web typecheck
pnpm --filter @ibex/operator-web test
pnpm --filter @ibex/operator-web lint
pnpm --filter @ibex/operator-web build
```

For the visual dashboard preview, enable the boundary explicitly before starting the dev server:

```bash
NEXT_PUBLIC_OPERATOR_WEB_PREVIEW=1 \
OPERATOR_WEB_DATA_MODE=preview OPERATOR_WEB_PREVIEW=1 \
pnpm --filter @ibex/operator-web dev
```

Without `NEXT_PUBLIC_OPERATOR_WEB_PREVIEW=1`, dashboard routes do not bypass the AuthService gate. The server layout additionally requires `OPERATOR_WEB_DATA_MODE=preview` and `OPERATOR_WEB_PREVIEW=1`; `NODE_ENV=production` always wins and disables preview. Preview data is deterministic and labelled in the dashboard controls; it is not a production data source.

## Surface classification

| Surface                                                                                                               | Status                        | Boundary                                                                                                                                                                                  |
| --------------------------------------------------------------------------------------------------------------------- | ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Transplanted sidebar, header, theme system, responsive layout, cards, charts, tables, dialogs, and route presentation | **Implemented presentation**  | Directly adapted from the supplied mock; only import, root-layout, route, and safety boundaries changed.                                                                                  |
| Overview and mock domain fixtures                                                                                     | **Preview-only**              | The mock fixture modules remain presentation fixtures. They are reachable only through an explicit preview build/runtime flag; production has no fixture adapter.                         |
| Login, signup, TOTP, and onboarding visuals                                                                           | **Specified-not-implemented** | AuthService owns credentials, sessions, refresh rotation, CSRF, MFA, organization membership, and secure cookies. The browser adapter is fail-closed and never mints or stores a session. |
| Dashboard shell in preview                                                                                            | **Preview-only**              | The transplanted shell can be inspected without fake authentication when `NEXT_PUBLIC_OPERATOR_WEB_PREVIEW=1`; it has no tenant authority and does not submit mutations.                  |
| Explore, sessions, memories, directives, incidents, drift, analytics, billing, settings data                          | **Deferred/live integration** | The mock route and visual states are retained. Live reads, authorization, mutations, evidence contracts, and upstream fetches are not claimed until owning APIs are connected.            |

## Security posture

There is no browser-side arbitrary upstream fetch, bearer credential, client-supplied organization authority, fake login, fake mutation success, or browser secret. `src/lib/auth/api.ts` is a fail-closed adapter that preserves the supplied auth UI and reports an unavailable AuthService rather than manufacturing credentials or sessions. `src/lib/preview-fixtures.ts` throws for production mode, and the dashboard layout is fail-closed unless all preview flags are present outside production; this boundary is covered by tests.

The copied mock demo code is intentionally classified as presentation-only. Theme/sidebar/onboarding preferences may use browser `localStorage`, the sidebar uses a non-auth layout cookie, and the drift banner uses `sessionStorage`; none is a credential or tenant-authority store. Demo APIs use in-memory fixture state, `Date.now`, `Math.random`, or simulated timers to make visual interactions convincing, including agent mutations, onboarding PAT/invite previews, and “first trace” completion. These are not real API calls and are reachable only from the explicitly gated preview subtree; they must be replaced by authenticated, tenant-scoped contracts before production integration.

## Verification and handoff

The supplied mock source is intentionally kept recognizable in `src/app`, `src/components`, and `src/lib`; unused failed custom shell components were removed by replacing the old source tree. Before live integration, connect AuthService and tenant-scoped API contracts at the server boundary, then replace fixture-only domain reads with validated, authorized responses while retaining the same presentation states.
