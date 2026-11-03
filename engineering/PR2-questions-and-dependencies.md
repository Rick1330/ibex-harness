# PR2, PR3, and Track D Questions and Dependencies

This sheet is the response form for the complete decision register in [the PR2 investigation note](pr2-evidence/investigation.md). The implementation has already completed two locally validated phases on `fix/IBEX-PR2-mounted-identity-authorization-assurance`:

- `5ebc6da` — route-policy parity, explicit environment profiles, non-development HMAC rejection, and AuthService-owned RS256 login/refresh.
- `1c204fd` — Python and Go JWT protected-header and required-claim hardening.
- Validation — 119 focused API tests passed; AuthService session-JWT and gRPC Go tests passed; Ruff passed.
- Installed tools — Go 1.25.13, Buf 1.47.2, Helm 3.19.0, ShellCheck 0.9.0, actionlint 1.7.12, golangci-lint 2.8.0, jq, and yq.

The branch now implements AuthService session validation, revocation, refresh-proof logout, and one-time action/session-bound step-up. Live AuthService/Redis integration and deployment behavior remain unverified; these are evidence gaps, not pending contract work.

## Required blocking answers

Please reply with **“accept all recommended defaults”** or provide exceptions by ID.

| ID | Default to accept or override |
|---|---|
| A1 | Operator is a policy/profile concept, not a fifth role; retain owner/admin/member/viewer. |
| A2 | Login/refresh/logout/me are browser-session routes; preserve existing bearer compatibility elsewhere unless explicitly migrated. |
| A3 | PR2/PR3 migrate only the operator and explicitly high-impact mounted surface, not every management route. |
| A4 | Use only existing permission constants; do not invent permission bits. |
| A5 | Preserve currently unambiguous authorization behavior and document every route gap for review. |
| A6 | Legal-hold set/clear use owner/admin + `LEGAL_HOLD_MANAGE` unless compliance requires owner-only. |
| B1 | Extend AuthService protobuf with explicit logout/revoke, access/session revocation, and step-up consume/bind operations. |
| B2 | Require `sid`, per-token `jti`, refresh-family `fid`, and distinct access/refresh kinds. |
| B3 | Redis-atomic refresh-JTI single-use consumption; replay revokes the full family. |
| B4 | Logout invalidates the current session, refresh family, and current access JTI; confirm whether logout-all-devices is also required. |
| B5 | Proposed TTLs: access 10 minutes, refresh 30 days, step-up 5 minutes; confirm or specify values. |
| B6 | One canonical issuer and audience per environment, asserted by API and AuthService. |
| B7 | Require `kid`, configured key selection, unknown-kid rejection, and overlapping-key rotation. |
| B8 | Require `typ=JWT` and exact `alg=RS256`; no HMAC outside development. |
| B9 | Proposed clock skew: 30 seconds; reject future `nbf` beyond skew. |
| B10 | Host-only secure cookies by default; shared domain only with explicit approval. |
| B11 | Step-up applies to all mounted routes whose existing permissions require it, plus legal-hold set/clear. |
| B12 | Step-up binds `sid`, subject, org, action, and expiry; consume JTI atomically immediately before mutation. |
| B13 | Browser high-impact actions require a verified operator session, not a PAT; approve a separate automation contract if needed. |
| B14 | Use stable action names such as `legal_hold.set`, `legal_hold.clear`, `operator.export`, and `operator.delete`. |
| D1 | Route policy is executable plus evidence: every mounted method/path has a row and dependency parity test. |
| D2 | Public routes are only explicitly marked health/readiness/metrics/docs routes; verify production metrics exposure separately. |
| D3 | Enforce Origin/Referer allow-list plus double-submit CSRF for cookie state changes. |
| D4 | SSE requires auth/permission, tenant filtering, `no-cache`, no proxy buffering, and bounded connection behavior. |
| D5 | Authenticated `/v1` responses use `Cache-Control: no-store`; SSE keeps its explicit streaming policy. |
| E1 | AuthService owns session/JTI state; API does not maintain a second authoritative revocation list. |
| E2 | Confirm the production Redis topology, persistence, timeout, namespace, and fail-closed requirements. |
| E3 | Use versioned Redis keys for refresh JTI, family, session, access JTI, and step-up JTI with documented TTLs/atomic operations. |
| E4 | Keep identity/organization/role ownership in existing AuthService/Core boundaries; no duplicate API identity authority. |
| E5 | Reject HMAC outside development; use explicit migration/kill-switch behavior for provisional local sessions. |
| E6 | Key rotation: publish new `kid`, overlap verification, rotate signer, retire old key after maximum token lifetime. |
| F1 | Define PR3 as lifecycle integration, executable high-impact policy, step-up mounting, and live integration tests. |
| F2 | Permit protobuf and migration changes when required, with compatibility and rollback notes. |
| F3 | Require unit, API, generated-proto, gRPC integration, Redis race/atomicity, Postgres authz, browser CSRF, SSE, and negative security tests. |
| F4 | Add Go race/property/fuzz tests for JTI use, JWT parsing, replay, malformed claims, and route parity. |
| F5 | Confirm repository CI coverage threshold or approve changed-line plus explicit security-case coverage. |
| F6 | Require structured redacted audit events for login, refresh, replay, logout, revoke, step-up, denial, and dependency degradation. |
| F7 | Define schema/proto backward compatibility, feature flags, key rollback, and safe disablement. |
| G1 | Provide the exact Track D checklist, owners, environments, and required artifacts; I will not infer Track D semantics. |
| G2 | Provide the staging/CI environment that can run API + AuthService + Redis + Postgres together. |
| G3 | Require TLS/ingress, forwarded-header, secure-cookie, origin, and proxy-buffering evidence. |
| G4 | Identify deployment mechanism, Helm/manifests, secret manager, service account, network policy, and rollback owner. |
| G5 | Confirm threat-model, dependency/SAST/secret-scan, DAST, penetration-test, and sign-off requirements. |
| G6 | Define availability/latency budgets, degraded-mode behavior, alert thresholds, and incident runbooks. |
| G7 | Define audit retention, access control, redaction, export/deletion, and compliance ownership. |
| G8 | Accept separate evidence labels: implemented, unit-tested, mounted-tested, live-tested, staging-verified, production-verified, blocked, unverified. |
| G9 | Confirm whether I may push the signed branch and open/update a PR after implementation; no settings or branch protections will be changed. |

## Minimal response template

```text
Accept all recommended defaults
Exceptions:
- B4 (logout-all-devices):
- B5 (TTL values):
- B10 (cookie domain):
- B13 (PAT automation):
- E2 (Redis topology):
- F1 (PR3 definition):
- G1 (Track D checklist):
- G2 (staging/CI runtime):
- G9 (push/PR permission):
```

Do not paste production secrets, private keys, or access tokens. Configuration values can be supplied as names, non-secret examples, or through an approved environment/connector.
