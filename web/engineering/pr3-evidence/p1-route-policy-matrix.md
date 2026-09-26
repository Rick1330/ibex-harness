# P1 mounted authorization matrix

**Baseline:** `main@1a1b89f` plus PR-3 source remediation on branch `fix/IBEX-PR3-pre-track-d-runtime-proof-p6-bootstrap`

This is an evidence register, not a claim that every route is an operator-session route. `bearer_pat` remains a legacy management-API contract only where explicitly approved; it is not a browser-equivalent identity for high-impact actions.

| Surface | Declared policy | Mounted guard | Local/contract evidence | Runtime/staging evidence | Owner / downstream gate |
|---|---|---|---|---|---|
| Operator login | PAT exchange into AuthService session | Login route and AuthService client | Tested in API session suite | Blocked: AuthService + browser origin/cookie | P0/P1 owner |
| Operator `/me` | Operator session | AuthService-backed session dependency | Tested | Blocked: staging revocation/expiry | P1/P6 |
| Operator refresh/logout | Operator session + CSRF for mutation | Session dependency + CSRF middleware | Tested | Blocked: cross-replica replay/logout | P1/P6 |
| Operator platform health | Operator session + metadata permission | `_require_operator_session` | Tested | Blocked: canonical runtime | P0/D1 |
| Operator SSE | Operator session + metadata permission | `require_operator_event_session` | Hub tests and route policy parity | Blocked: ingress buffering, reconnect, slow client, drain | P0/P6/E2 |
| Legal-hold set/clear | Browser high-impact action; owner/admin + `LEGAL_HOLD_MANAGE` + session-bound step-up + CSRF/origin | `RequireLegalHoldManage` now requires a verified operator access cookie, DB owner/admin role, session-bound one-time `legal_hold.manage` step-up, and operator-scoped DB session | 50 focused auth/session/legal-hold tests pass; route inventory and policy rows updated | Blocked: AuthService cross-replica revocation, browser CSRF/origin, two-tenant staging evidence | P1/P3 owner |
| Provider/model policy/capture policy | Existing management permission contract | Bearer-PAT dependencies | Unit/route tests | Blocked: route-level tenant/runtime matrix | P1/P2/P3 |
| Organization/user/agent/token mutations | Existing management permission contract | Bearer-PAT dependencies | Unit/integration tests | Blocked: two-tenant runtime matrix; high-impact mutations require follow-up session/step-up migration | P1 / management API owner |
| Raw/export/delete/replay/secret-use | High-impact taxonomy | Not uniformly mounted as operator routes | Partial helper coverage | Blocked; no D1 exposure permitted | P1/P2/P3/D2-D5 |

## Required evidence labels

Each row must be upgraded independently from `declared` to `mounted`, `contract-tested`, `runtime-tested`, and `staging-verified`. A route inventory row or helper definition does not advance the evidence state.

## Legal-hold decision gate — resolved for browser scope

**Decision:** adopt the **operator-session contract** for browser mutations. Every set/clear request must carry a verified AuthService operator session with non-empty subject, org, session ID, and permissions. The caller must be an active database owner/admin with `LEGAL_HOLD_MANAGE`; the `legal_hold.manage` step-up is bound to that same session and atomically consumed; cookie CSRF/origin middleware remains mandatory. A PAT plus `X-IBEX-Step-Up` is not a browser-equivalent path.

**Automation:** no implicit PAT automation path is accepted by the browser route. If automation is required later, it must be a separately named API-only route with a service identity, action-specific proof, redacted audit actor, no session-cookie access, and its own route-policy/evidence row. That follow-up route is not part of D1.

**Remaining gate:** source enforcement is implemented, but the decision is not fully closed until hosted AuthService/Redis/PostgreSQL and browser staging evidence proves revoked-session denial, one-time step-up replay denial, CSRF/origin denial, cross-tenant denial, audit subject binding, and no side effect on dependency failure.
