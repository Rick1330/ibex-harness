# P1 mounted authorization matrix

**Baseline:** `main@1a1b89f`

This is an evidence register, not a claim that every route is an operator-session route. `bearer_pat` is retained only where the existing management API contract permits it; high-impact browser mutations require a separate decision.

| Surface | Declared policy | Mounted guard | Local/contract evidence | Runtime/staging evidence | Owner / downstream gate |
|---|---|---|---|---|---|
| Operator login | PAT exchange | `get_validator` on login | Tested in API session suite | Blocked: AuthService + browser origin/cookie | P0/P1 owner |
| Operator `/me` | Operator session | AuthService-backed session dependency | Tested | Blocked: staging revocation/expiry | P1/P6 |
| Operator refresh/logout | Operator session + CSRF for mutation | Session dependency + CSRF middleware | Tested | Blocked: cross-replica replay/logout | P1/P6 |
| Operator platform health | Operator session + metadata permission | `_require_operator_session` | Tested | Blocked: canonical runtime | P0/D1 |
| Operator SSE | Operator session + metadata permission | `require_operator_event_session` | Hub tests and route policy parity | Blocked: ingress buffering, reconnect, slow client, drain | P0/P6/E2 |
| Legal-hold set/clear | High-impact action; owner/admin + `LEGAL_HOLD_MANAGE` + step-up | `RequireLegalHoldManage` currently starts from bearer PAT and conditionally resolves operator session only when proof is supplied | Negative step-up tests exist | Blocked pending PAT-vs-session decision and runtime proof | P1/P3 owner |
| Provider/model policy/capture policy | Existing management permission contract | Bearer-PAT dependencies | Unit/route tests | Blocked: route-level tenant/runtime matrix | P1/P2/P3 |
| Organization/user/agent/token mutations | Existing management permission contract | Bearer-PAT dependencies | Unit/integration tests | Blocked: two-tenant runtime matrix | P1 / management API owner |
| Raw/export/delete/replay/secret-use | High-impact taxonomy | Not uniformly mounted as operator routes | Partial helper coverage | Blocked; no D1 exposure permitted | P1/P2/P3/D2-D5 |

## Required evidence labels

Each row must be upgraded independently from `declared` to `mounted`, `contract-tested`, `runtime-tested`, and `staging-verified`. A route inventory row or helper definition does not advance the evidence state.

## Legal-hold decision gate

Before browser integration, choose one of these explicit contracts:

1. **Operator-session contract (recommended):** verified AuthService session supplies subject, org, session ID, permissions, CSRF, and step-up binding; the mutation does not accept a PAT-only browser path.
2. **Automation contract:** PAT use is explicitly documented as non-browser automation, binds an authenticated service identity and action-specific step-up, records redacted audit identity, and is excluded from the browser D1 shell until staging evidence exists.

No implementation may imply option 1 while continuing to accept option 2 implicitly.
