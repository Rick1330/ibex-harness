# IBEX Operator Web Service (`@ibex/operator-web`)

This directory contains the IBEX operator web **service**. Its JavaScript manifest (`package.json`) exists to build and run the service; the architectural boundary is the service, not a reusable library package. Its presentation layer is a **faithful transplant of the supplied dashboard mock** at `/home/ubuntu/dash-board-mock/dash-board-mock`: the same Geist/mono/serif typography, neutral surface tokens, sidebar/header chrome, responsive spacing, cards, charts, tables, dialogs, navigation, auth atmosphere, onboarding composition, and domain route structure are kept directly rather than re-created as a simplified shell.

## Local use

From the repository root:

```bash
pnpm --filter @ibex/operator-web dev
pnpm --filter @ibex/operator-web typecheck
pnpm --filter @ibex/operator-web test
pnpm --filter @ibex/operator-web lint
pnpm --filter @ibex/operator-web build
```

For the visual dashboard shell, start the service and open `/dashboard` directly:

```bash
pnpm --filter @ibex/operator-web dev
```

The current shell intentionally has no login route or demo credentials. AuthService, tenant authority, session cookies, MFA, and authenticated mutations are deferred; the dashboard is directly reachable so the presentation can be inspected independently.

## Surface classification

| Surface                                                                                                               | Status                        | Boundary                                                                                                                                                                                  |
| --------------------------------------------------------------------------------------------------------------------- | ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Transplanted sidebar, header, theme system, responsive layout, cards, charts, tables, dialogs, and route presentation | **Implemented presentation**  | Directly adapted from the supplied mock; only import, root-layout, route, and safety boundaries changed.                                                                                  |
| Overview and mock domain fixtures                                                                                     | **Preview-only**              | The mock fixture modules remain presentation fixtures. They are reachable only through an explicit preview build/runtime flag; production has no fixture adapter.                         |
| Login, signup, and TOTP credential flows                                                                               | **Removed/deferred**          | No credential entry, demo password, token minting, or MFA enrollment is exposed in this shell. AuthService owns the future implementation.                                               |
| Dashboard shell                                                                                                       | **Presentation-only**         | The shell is directly reachable for inspection; it has no tenant authority and authenticated mutations remain disabled.                                                             |
| Explore, sessions, memories, directives, incidents, drift, analytics, billing, settings data                          | **Deferred/live integration** | The mock route and visual states are retained. Live reads, authorization, mutations, evidence contracts, and upstream fetches are not claimed until owning APIs are connected.            |

## Security posture

There is no browser-side arbitrary upstream fetch, bearer credential, client-supplied organization authority, fake login, or browser secret. The auth context is credential-free and exists only to preserve future step-up integration seams; it never loads, manufactures, or stores a session. Token issuance, bearer-curl generation, and TOTP enrollment are not exposed.

The copied mock code is intentionally classified as presentation-only. Theme/sidebar/onboarding preferences may use browser `localStorage`, the sidebar uses a non-auth layout cookie, and the drift banner uses `sessionStorage`; none is a credential or tenant-authority store. Authenticated API reads, mutations, token issuance, invites, and first-trace traffic must be replaced by validated tenant-scoped contracts before production integration.

## Verification and handoff

The supplied mock source is intentionally kept recognizable in `src/app`, `src/components`, and `src/lib`; unused failed custom shell components were removed by replacing the old source tree. Before live integration, connect AuthService and tenant-scoped API contracts at the server boundary, then replace fixture-only domain reads with validated, authorized responses while retaining the same presentation states.
