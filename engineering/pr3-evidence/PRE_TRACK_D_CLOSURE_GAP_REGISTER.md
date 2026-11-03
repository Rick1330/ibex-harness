# Pre-Track-D closure gap register

**Revision under review:** `fix/IBEX-PR3-pre-track-d-runtime-proof-p6-bootstrap`

This register is the release boundary for Track D. A source change, unit test, mock console, Helm render, or desired GitHub policy is not staging/runtime evidence.

## Source gaps addressed in this remediation

| Area | Change | Evidence | Remaining boundary |
|---|---|---|---|
| Legal-hold decision gate | Browser set/clear now require a verified operator access session, non-empty subject/org/session ID/permissions, active owner/admin DB role, `LEGAL_HOLD_MANAGE`, session-bound one-time `legal_hold.manage` step-up, and operator-scoped DB session. | API auth/session/legal-hold suite: 50 focused tests; route-policy parity passes. | Hosted AuthService revocation/replay, CSRF/origin, tenant-negative, audit-subject, and no-side-effect staging evidence. |
| Legal-hold audit identity | `set_by`/`cleared_by` use the verified session subject. PAT plus `X-IBEX-Step-Up` is not treated as browser authentication. | Route and evidence matrix updated. | Separate automation route, if needed, requires a future service-identity contract and is excluded from D1. |
| Session binding | Verified local/remote operator sessions now expose subject and bind request state used by step-up verification. | Operator session tests pass. | AuthService cross-replica/revocation proof is external. |
| Worker readiness | Added bounded Redis-backed `/ready`; `/health` remains liveness; Helm worker readiness now uses `probes.readinessPath`. | Worker enqueue suite: 27 passed. | Real Redis HA/failover/drain staging evidence. |
| P6 manifest | Validator now requires explicit evidence state, rejects applicable failed/skipped/missing/unknown/cancelled checks, rejects expected inapplicable checks, validates immutable artifact URI schemes, and the CI guard executes a revision-bound manifest. | P6 guard and JSON validation pass. | Closed inventory, artifact existence/hash verification in hosted CI, and staging evidence collection. |
| Console boundary | Unknown dashboard paths fail closed as deferred; route inventory covers current dashboard surfaces; mock settings shows an unavailable boundary outside explicit preview mode. | Console lint, typecheck, 13 tests, and production build pass. | Authenticated D1 DAL, real DTO/SSE contracts, Playwright/a11y, and staging cutover. |
| Route policy | Legal-hold route declarations and generated inventory now identify the operator-session/action contract. | Route-policy tests pass. | Complete taxonomy/migration for all remaining destructive and secret-use routes. |

## Remaining actionable source work before D1

These remain **release blockers** even though they are not external infrastructure by themselves:

1. Implement the authenticated D1 server DAL/BFF for context, Overview, platform health, freshness/completeness, and SSE; remove `mockSummary`, `mockTrends`, `mockActivity`, and `SHELL_HEALTH` from any production path.
2. Add typed/versioned DTOs and SSE envelopes, generated TypeScript client freshness, parser wiring, bounded timeout/error/retry behavior, request-ID propagation, and no-store semantics.
3. Expand the high-impact action taxonomy and migrate organization delete, provider-secret use, token delete, raw/export/replay, and other privileged browser actions to mandatory operator session + permission + action-bound step-up + CSRF/origin + tenant binding + audit identity.
4. Restrict provider credential decryption to the provider-resolution service identity; ordinary management PATs, agent/chat tokens, wrong-org callers, and missing service identity must never receive plaintext keys.
5. Add complete two-tenant/four-role API integration coverage, including wrong path/token/session org, revoked session, service-account scope, RLS transaction scope, and non-Postgres org predicates.
6. Make route-policy parity authoritative for dependency class, permission, action, step-up, CSRF/origin, tenant source, and evidence state; fail on missing, stale, weaker, or downgraded mounted dependencies.
7. Add authenticated operator Playwright, axe/WCAG, keyboard/focus, reduced-motion, responsive, visual, SSE reconnect/drain, and performance checks with immutable artifacts.
8. Add app loading/error/not-found boundaries, redacted request-ID UX, and production CSP/HSTS/referrer/content-sniffing/frame-ancestor headers.
9. Add executable P6 required-check inventory, artifact provenance and evidence-state promotion rules, generated-client checks, operator E2E/a11y/visual contexts, and rollback-evidence contexts.
10. Replace startup-only or liveness-masked readiness assumptions everywhere; API and worker readiness must turn false on dependency loss and true on recovery within bounded budgets.
11. Choose and document managed versus chart-owned PostgreSQL/Redis ownership, endpoints, HA/failover, TLS/auth, backup/restore, readiness, and secret rotation.
12. Publish a digest-pinned migration image and test expand/contract, N/N+1, idempotent forward migration, and rollback compatibility against disposable PostgreSQL.

## External blockers that cannot be manufactured in Git

| External gate | Required owner action | Required evidence artifact |
|---|---|---|
| Canonical topology | Provision staging API/console/AuthService/SSE origins, DNS, TLS renewal, ingress, trusted forwarded headers, and rollback owner. | Rendered manifests + HTTPS login/API/SSE/deep-link/rollback transcript. |
| AuthService/secret manager | Mount RS256 session lifecycle, refresh/logout/revocation/step-up; provision and rotate AuthService credentials, JWT keys, CSRF secret, Redis credentials, and provider-key master key. | Revision-bound secret-delivery/rotation and cross-replica revocation evidence with no secret values. |
| Runtime tenant/security matrix | Run two organizations/four roles against real AuthService, PostgreSQL/RLS, Redis, ClickHouse/object storage and API. | Negative matrix: wrong org/path/token/session, revoked session, replayed step-up, CSRF/origin, no existence leakage. |
| SSE edge behavior | Verify proxy buffering, read/write/idle limits, flush boundaries, Last-Event-ID, deduplication, slow client, reconnect, expired session, and drain. | Browser/network trace + server metrics + immutable P6 manifest artifact. |
| Images/supply chain | Publish real signed digest-pinned images, image-bound SBOM/provenance, and run Kyverno clean-cluster rejection/acceptance soak. | Digest manifest, SBOM/provenance/signature references, Kyverno rejection and acceptance logs. |
| Migration/recovery | Run disposable/staging expand/contract and pgBackRest WAL/PITR drills; measure RPO/RTO and tenant isolation after restore. | Migration compatibility record + signed PITR/RPO/RTO/rollback evidence. |
| GitHub enforcement | Apply non-zero approving-review requirement, CODEOWNERS/stale-review policy, required contexts, and query live branch protection. | Live API response and hosted check URLs for the exact revision. |
| Legacy dashboard cutover | Run compatibility parity, coexistence duration, deep links, SSE, rollback, and public docs unaffected checks; retain legacy until retirement criteria pass. | Cutover/rollback evidence and dated retirement signoff. |

## Track-D entry decision

Track D may begin only for a **read-only, explicitly preview/unavailable console slice** if Product/Architecture records that D1 is presentation work and all live data/mutation affordances remain disabled. Track D may **not** claim authenticated operator-runtime completion, live health/freshness, tenant safety, legal-hold completion, SSE readiness, or production rollout until the applicable source gaps and external evidence above are complete.

Any P0 result involving fail-open authorization, tenant leakage, secret exposure, unsafe deletion, unverified restore, or unsigned image admission stops rollout and disables the affected capability.
