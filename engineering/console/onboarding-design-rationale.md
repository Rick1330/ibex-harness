# Onboarding / first-run

Dismissible checklist on Overview until required steps (agent → PAT → test
request) complete. Optional invite + budget. Collapses to sidebar
**Setup guide** — never a one-shot modal.

## Trigger

Derived: `countOrgAgents(org) === 0` (no `has_completed_onboarding` column).
Progress persisted under `ibex.onboarding.v1.{orgId}` (settings-shaped store).

## Honesty

- No demo data injected to fake a populated org.
- PAT secret once; scopes = ADR-0009 bitmap constants only.
- Invite stays `status: invited` until accept.
- Drift empty states name the 7+ day baseline requirement.
- Cross-tenant proxy failures are `403`, not `404` — troubleshooting copy says so.

## Wiring

- Step 1: `POST /v1/agents` via `createAgent`
- Step 2: fixture PAT issue (Settings-compatible shape)
- Step 3: curl + Explore poll / simulate
- Step 4: `createUserInvite`
- Step 5: deep-link Billing `#budgets`
