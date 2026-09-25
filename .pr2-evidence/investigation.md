# PR2 Investigation Note

## Baseline

The working branch is `fix/IBEX-PR2-mounted-identity-authorization-assurance` at `df657fd2436b6d7646b9c491b429a23634d22750`, which is the merged PR1 commit. The checkout was clean before implementation work.

The API development environment was installed with `uv sync --extra dev` under `services/api`. Python 3.12.3, pytest 9.1.1, and Ruff 0.16.5 are available. The sandbox has no Docker or Podman executable and no local Postgres, Redis, AuthService, or related listeners were detected.

The approved validation tools are installed: Go 1.25.13, Buf 1.47.2, Helm 3.19.0, ShellCheck 0.9.0, actionlint 1.7.12, golangci-lint 2.8.0, jq 1.7, and Debian yq 0.0.0. Go and generated protobuf bindings are local validation tooling only; generated bindings under `packages/proto/gen/` are not committed by repository policy.

## AuthService operator-session contract trace

| Layer | Evidence | Result |
|---|---|---|
| Protobuf source | `packages/proto/proto/ibex/auth/v1/auth.proto:49-50,231-242` | `IssueOperatorSession` exists. Empty `refresh_token` issues for the authenticated PAT caller; non-empty `refresh_token` rotates an RS256 pair. |
| Generated gRPC bindings | Ephemeral `packages/proto/gen/go/ibex/auth/v1/auth_grpc.pb.go` generated with `buf generate`; client interface includes `IssueOperatorSession`. | Contract generation succeeds. Generated output is uncommitted by policy. |
| Server registration | `services/auth/cmd/auth/main.go:477-518` | `registerAuthGRPC` constructs `grpcserver.Server`, passes `SessionIssuer`, and calls `authv1.RegisterAuthServiceServer`. |
| Concrete RPC | `services/auth/internal/grpc/totp_session.go:120-172` | The RPC issues from caller context or calls `RefreshPair`; errors map to gRPC status codes. |
| Server construction | `services/auth/internal/grpc/server.go:41-100` | `SessionIssuer` is an optional dependency. Missing issuer returns `FailedPrecondition` at RPC use. |
| Composition/bootstrap | `services/auth/cmd/auth/main.go:162-234,254-267` | `newSessionIssuer` reads `JWT_PRIVATE_KEY_PEM`, issuer, audience, and TTLs. When signing is enabled, Redis JTI storage is required and attached. |
| API transport | `services/api/app/auth/session_refresh.py:18-86` | The API calls `/ibex.auth.v1.AuthService/IssueOperatorSession` directly for refresh rotation and maps gRPC failures. |
| API configuration | `services/api/app/config.py:31-35,71-107` | Auth gRPC address, issuer, audience, public keys, and provisional HMAC settings exist. Environment profile is not yet explicit in API settings. |
| Tests | `services/auth/internal/sessionjwt/*_test.go`, `services/auth/internal/grpc/totp_session_test.go`, `services/api/tests/unit/operator/*session*.py` | Go session JWT and gRPC unit tests pass. API focused session/step-up tests pass. No live AuthService/Redis/Postgres runtime evidence is available. |

The contract is internally consistent for issuance and refresh. It is **not lifecycle-complete for PR2**: the protobuf has no operator logout, session revocation, access-JTI revocation, or step-up-JTI consumption RPC. PR2 must not invent an incompatible RPC silently. Those lifecycle claims remain blocked until the project’s intended AuthService contract is extended and registered or an existing contract is identified.

## Current API gaps confirmed

The mounted API session router in `services/api/app/routers/session.py` still:

- mints HS256 access and refresh cookies locally on login;
- dispatches refresh based on the unverified JWT `alg` header;
- permits HMAC verification where configured;
- verifies cookie sessions through the provisional Python verifier; and
- clears cookies on logout without server-side invalidation.

The Go verifier in `services/auth/internal/sessionjwt/verifier.go` verifies signatures and basic issuer/audience/kind/expiry claims but does not currently enforce JWT header `alg`, `typ`, `kid`, key selection, not-before policy, or all required claims.

The step-up dependency in `services/api/app/step_up.py` is helper-level. It verifies a token and sets mutable request state but does not consume the JTI atomically, bind action/session, or mount on legal-hold mutations.

## Mounted route inventory

The complete route inventory is generated at `.pr2-evidence/route_inventory.json` and rendered at `.pr2-evidence/route_inventory.txt`. FastAPI 0.141 represents included routers as `_IncludedRouter` objects, so the evidence script traverses `original_router.routes` to enumerate actual mounted endpoints.

The inventory contains the mounted management, operator session, platform, SSE, legal-hold, provider, model-policy, billing, capture-policy, rate-limit, token, user, agent, organization, and health/readiness routes. It is a source inventory, not yet the checked-in route-policy contract required by PR2.

## Baseline validation

- API focused session/step-up tests: **77 passed**.
- Go session JWT package tests: **passed**.
- Go AuthService gRPC package tests: **passed**.
- Buf generation: **passed**.
- Runtime integration with real AuthService, Redis, and Postgres: **blocked** because no supported local services or container runtime are available.

## Evidence boundary

Local unit and mounted TestClient tests are contract evidence. Generated bindings and in-memory or fake dependencies do not prove runtime behavior. No staging, production, P1, P0, P6, D0, D1, TLS, ingress, branch-protection, or external deployment claim is made by this note.

## Immediate implementation order

1. Add an explicit API environment profile and reject HMAC operator sessions outside local development.
2. Replace API login’s local HMAC issuance with the existing AuthService operator-session RPC transport, without inventing lifecycle RPCs.
3. Harden the Python and Go JWT verification contracts against the PR2 claim/header requirements that can be implemented from the current contract.
4. Add a checked-in route-policy inventory and parity test.
5. Replace mutable step-up success state with an ordered, explicit dependency on currently mounted high-impact routes where the current contract supports it; record missing JTI consumption/session binding as blocked if no AuthService/storage contract exists.
6. Run focused tests after each phase and create DCO-signed local commits.

## Implemented phases

Commit `5ebc6da` adds the checked-in 60-route policy inventory and parity test, explicit `IBEX_ENV` profiles, fail-closed staging/production configuration, and AuthService-owned operator login/refresh transport outside development. Commit `1c204fd` hardens Python and Go JWT verification against algorithm/type confusion and malformed core claims; refresh claims must include a family identifier in the Go verifier.

Focused validation after both commits: 119 API tests passed with two non-failing dependency warnings; `go test ./services/auth/internal/sessionjwt/... ./services/auth/internal/grpc/...` passed; Ruff passed on changed Python modules. No generated protobuf output was committed.

## Remaining PR2 blockers

The current AuthService protobuf has issuance and refresh only. It does not expose an operator logout/revoke RPC, an access-JTI revocation/check RPC, or a step-up consume-and-bind RPC. The current Go JTI store can support refresh-family rotation, but there is no contract path for API logout or one-time step-up consumption. The API’s current step-up token also lacks action and session-binding claims. Implementing those requirements now would require changing the protobuf schema, generated clients, server registration, persistence contract, and integration tests; this is recorded as a deliberate blocker rather than an invented private protocol.

Runtime staging evidence remains unavailable because the sandbox has no container runtime and no live AuthService, Redis, or Postgres endpoints. The branch therefore contains unit/contract enforcement and reproducible evidence, not a claim of live deployment readiness.

## Complete PR2–PR3–Track D decision register

The following questions are intentionally consolidated here so implementation does not silently choose product, protocol, threat-model, deployment, or evidence semantics. A response of **“accept all recommended defaults”** is sufficient unless an item is changed. Items marked **blocking** materially change the wire contract, security behavior, data model, deployment topology, or acceptance evidence. Items marked **non-blocking** can use the recommendation and be recorded in the implementation log.

### A. Product identity and authorization semantics

| ID | Decision required | Recommendation | Priority |
|---|---|---|---|
| A1 | What does “operator” mean? | Keep `operator` as a policy/profile concept; do not add a fifth role. Use the existing owner/admin/member/viewer roles plus explicit permission bits. | Blocking |
| A2 | Which routes are operator-session-only versus PAT/bearer-compatible? | Login, refresh, logout, and session-me are browser-session routes. Preserve bearer compatibility only where already mounted and document every exception. | Blocking |
| A3 | Should the API migrate all management routes to cookie sessions in PR2, or only the operator surface? | Limit PR2 to the mounted operator surface and explicit high-impact mutations; do not silently migrate all bearer APIs. | Blocking |
| A4 | Which permission is canonical for each route family? | Map existing constants only: metadata read, raw read, export, delete, replay, secret use, legal-hold manage, org settings, user manage, and related existing bits. Do not invent permissions. | Blocking |
| A5 | What is the intended behavior for routes currently lacking a narrow permission? | Preserve current behavior until row-by-row review; record the gap rather than guessing a stricter business policy. | Blocking |
| A6 | Should legal-hold set and clear require owner only, or owner/admin with `LEGAL_HOLD_MANAGE`? | Use the existing owner/admin + `LEGAL_HOLD_MANAGE` policy unless compliance requires owner-only. | Blocking |
| A7 | What is the anti-enumeration contract? | Cross-organization, missing-object, and unauthorized-object cases should return the same not-found shape where the existing API already follows that pattern. | Non-blocking |

### B. Session and JWT protocol

| ID | Decision required | Recommendation | Priority |
|---|---|---|---|
| B1 | May the AuthService protobuf be extended for complete PR2 lifecycle semantics? | Yes. Add explicit RPCs rather than private HTTP/gRPC methods: issue/refresh, logout/revoke session, validate/revoke access JTI as needed, and consume step-up. | Blocking |
| B2 | Which session identifiers are required? | Include `sid` for the session, `jti` for each token, and `fid` for the refresh family. Keep access and refresh token kinds distinct. | Blocking |
| B3 | What is the refresh replay policy? | Redis-atomic single-use refresh JTI consumption; any reuse revokes the complete family and fails closed. | Blocking |
| B4 | What does logout invalidate? | At minimum the current session (`sid`), its refresh family, and the current access JTI. Confirm whether logout-all-devices is also required in PR2. | Blocking |
| B5 | What are access and refresh TTLs? | Use AuthService-configured values; proposed defaults are access 10 minutes, refresh 30 days, step-up 5 minutes, with environment-specific overrides. | Blocking |
| B6 | What are issuer and audience values? | One canonical issuer and audience per environment, supplied by configuration and asserted by both Python and Go verifiers. | Blocking |
| B7 | Is `kid` mandatory now? | Yes. Every RS256 JWT must carry `kid`; verification must select only configured keys, reject unknown kids, and support overlapping old/new keys during rotation. | Blocking |
| B8 | Is `typ=JWT` mandatory? | Yes, in addition to exact `alg=RS256` for AuthService-issued sessions. `alg=none`, HS256 fallback, and algorithm dispatch from untrusted headers are prohibited outside development. | Blocking |
| B9 | What is the clock-skew allowance and `nbf` policy? | Reject future `nbf` beyond a small configured skew; proposed skew is 30 seconds. Record the value in configuration and tests. | Non-blocking |
| B10 | What should local development permit? | HMAC may remain only behind an explicit development profile and must be impossible when `staging` or `production` is selected. | Non-blocking |
| B11 | Are refresh and access cookies host-only or shared-domain? | Prefer host-only cookies; allow a shared domain only by explicit configuration and security review. | Blocking |
| B12 | Cookie settings? | Production: `Secure`, `HttpOnly`, `SameSite=Lax` unless a documented cross-site requirement forces `None`; use `__Host-` names where domain/path constraints permit. | Non-blocking |
| B13 | Logout response semantics? | Always clear browser cookies with matching attributes and return an idempotent success shape, while AuthService invalidation is fail-closed or explicitly policy-defined. | Blocking |

### C. Step-up and high-impact action semantics

| ID | Decision required | Recommendation | Priority |
|---|---|---|---|
| C1 | Which mounted routes require step-up? | All currently mounted routes whose existing permission constants declare step-up, plus legal-hold set/clear. Do not claim coverage for unmounted future routes. | Blocking |
| C2 | How is step-up bound? | Bind to `sid`, `sub`, `org_id`, declared action, and a short expiry. The action must be explicit and cannot be inferred from a generic boolean request flag. | Blocking |
| C3 | Is step-up one-time? | Yes. Consume the step-up JTI atomically in AuthService/Redis immediately before the protected mutation. | Blocking |
| C4 | What happens on missing, expired, reused, mismatched, or unavailable step-up? | Deny with a stable insufficient-authentication error; do not execute the mutation; unavailable backing storage must fail closed. | Non-blocking |
| C5 | Can step-up be satisfied by a PAT bearer token? | Recommendation: no for browser high-impact actions; require a verified operator session. If PAT step-up is required for automation, define a separate non-browser service contract. | Blocking |
| C6 | Which action names are canonical? | Use stable names such as `legal_hold.set`, `legal_hold.clear`, `provider_credential.write`, `operator.export`, and `operator.delete`; record them in the route policy. | Blocking |
| C7 | Does step-up require TOTP only? | Use the existing TOTP implementation for PR2; do not add WebAuthn or external MFA until a separate contract is approved. | Non-blocking |

### D. Route policy, middleware, and browser boundaries

| ID | Decision required | Recommendation | Priority |
|---|---|---|---|
| D1 | Should route policy be executable or evidence-only? | Make it both: checked-in machine-readable policy plus parity tests that every mounted route has a row and every protected row has executable dependency coverage. | Blocking |
| D2 | Which routes are public? | Only health/readiness/metrics and documentation routes explicitly marked public; verify metrics exposure separately for production. | Non-blocking |
| D3 | CSRF policy? | Enforce Origin/Referer allow-list and double-submit CSRF for state-changing browser-cookie requests; exempt only health/readiness and explicitly non-browser routes. | Blocking |
| D4 | SSE policy? | Require operator authentication and permission, set `no-cache`, `X-Accel-Buffering: no`, bounded connection behavior, and tenant-scoped event filtering. | Blocking |
| D5 | Cache policy? | All authenticated `/v1` responses default to `Cache-Control: no-store`; SSE uses its explicit streaming policy. | Non-blocking |
| D6 | CORS policy? | Explicit origins only, credentials only where needed, never wildcard with credentials, and a tested preflight contract. | Non-blocking |
| D7 | Error policy? | Stable API error codes; no token, key, Redis, SQL, or organization-existence leakage in messages or logs. | Non-blocking |

### E. AuthService, storage, and data model

| ID | Decision required | Recommendation | Priority |
|---|---|---|---|
| E1 | Which datastore owns session state? | AuthService owns session/JTI state; API does not maintain a second authoritative revocation list. | Blocking |
| E2 | Redis durability and topology? | Production Redis with persistence/replication appropriate to the deployment; define timeout, fail-closed behavior, and namespace/version. | Blocking |
| E3 | Redis key schema? | Versioned keys for refresh JTI, family, session, access JTI, and step-up JTI; document TTLs and atomic Lua/transaction operations. | Blocking |
| E4 | Postgres ownership? | Keep identity/organization/role data in the existing AuthService/Core ownership boundaries; no duplicate API-side identity authority. | Blocking |
| E5 | What is the migration strategy for provisional HMAC sessions? | Reject them outside development; in development, make migration explicit and never accept HS256 as RS256. | Non-blocking |
| E6 | Key rotation process? | Generate new key pair, publish public key with new `kid`, overlap verification window, rotate signing key, then retire old key after maximum token lifetime. | Blocking |

### F. PR3 scope and quality gates

| ID | Decision required | Recommendation | Priority |
|---|---|---|---|
| F1 | What exactly is PR3? | Treat PR3 as the next enforcement tranche: complete route-policy executable coverage, high-impact step-up mounting, session lifecycle integration, and live integration tests. | Blocking |
| F2 | Is PR3 allowed to change protobuf and migrations? | Yes, if required to close the lifecycle gaps; protobuf and schema changes must include compatibility and rollback notes. | Blocking |
| F3 | Required test layers? | Unit, API contract, generated-proto contract, AuthService gRPC integration, Redis atomicity/race, Postgres authorization, browser-cookie/CSRF, SSE, and negative security tests. | Non-blocking |
| F4 | Race and property testing? | Add Go race tests for JTI consumption and property/fuzz tests for JWT parsing, refresh replay, malformed claims, and route-policy parity. | Non-blocking |
| F5 | Required coverage threshold? | Preserve repository CI thresholds; if none exists, propose changed-line coverage plus explicit security-case coverage rather than an arbitrary global number. | Blocking |
| F6 | Observability requirements? | Structured audit events for login, refresh, refresh replay, logout, revoke, step-up success/failure, authorization denial, and degraded dependencies; never log raw tokens or secrets. | Blocking |
| F7 | Rollback behavior? | Define schema/proto backward compatibility, feature flags, key rollback, and safe disablement that cannot re-enable HMAC in staging/production. | Blocking |

### G. Track D release and operational evidence

| ID | Decision required | Recommendation | Priority |
|---|---|---|---|
| G1 | What does “Track D” mean operationally? | Confirm the exact Track D checklist, owners, environments, and required artifacts; do not infer it from PR2/PR3 names. | Blocking |
| G2 | Which environment authorizes release evidence? | Name the staging environment and service endpoints or CI workflow that can run AuthService + Redis + Postgres + API together. | Blocking |
| G3 | TLS and ingress evidence? | Require real TLS termination, forwarded-header policy, secure-cookie behavior, origin allow-list behavior, and proxy buffering tests. | Blocking |
| G4 | Deployment ownership? | Identify the deployment mechanism, manifests/Helm chart, secret manager, service account, network policy, and rollback owner. | Blocking |
| G5 | Security review? | Confirm required threat-model review, dependency/SAST/secret scanning, DAST, penetration-test scope, and sign-off owners. | Blocking |
| G6 | Availability targets? | Define AuthService/Redis latency and availability budgets, degraded-mode behavior, alert thresholds, and incident runbooks. | Blocking |
| G7 | Data retention and audit requirements? | Define audit-event retention, access controls, redaction, export/deletion rules, and compliance owner. | Blocking |
| G8 | Evidence acceptance? | Accept separate labels for implemented, unit-tested, mounted-tested, live-integration-tested, staging-verified, production-verified, blocked, and unverified. | Non-blocking |
| G9 | GitHub action? | Confirm whether I may push the signed branch and open/update a PR after implementation. No repository settings or branch protections will be changed without explicit instruction. | Blocking |

## Proposed default answer

Unless the project owner overrides an item, the implementation will use: **A1–A3** policy/profile operator semantics; explicit existing permissions; AuthService-owned RS256 sessions; `sid`/`jti`/`fid`/`kid`; atomic Redis replay consumption; logout invalidation; action- and session-bound one-time step-up; strict browser CSRF/origin and no-store headers; host-only secure cookies; exhaustive route-policy parity; protobuf/schema changes where necessary; layered tests; and separate local versus live/staging evidence. Track D will remain blocked until its checklist, runtime environment, owners, and release evidence are supplied.

## Response template

```text
Accept all recommended defaults
Exceptions:
- A1:
- A2:
- A3:
- A6:
- B4:
- B5:
- B11:
- C1:
- C5:
- D4:
- E2:
- F1:
- G1:
- G2:
- G9:
```

## Final execution status

The final execution tranche added the AuthService lifecycle RPCs `ValidateOperatorSession`, `RevokeOperatorSession`, and `ConsumeStepUp`, server-side session/access/family/step-up state operations, explicit `sid`/`fid`/`kid`/action bindings, AuthService-backed API validation and logout, ordered action-bound step-up dependencies, executable route-policy dependency parity, production Origin/Referer checks, authenticated response cache headers, SSE anti-buffering headers, and malformed-token fuzz coverage. The complete API suite passes with 605 passed and 10 skipped tests. The complete AuthService suite, Go vet, Go race suite, JWT fuzz campaign, Ruff, Buf lint, scoped breaking check, and ephemeral generation pass.

The coverage evidence is deliberately separated: full API coverage is 94.17% against the repository fail-under target of 95%; diff-cover against the complete origin/main delta reports 62%. These are validation shortfalls, not claims of passing gates. The remaining coverage work is concentrated in new transport error branches, non-development cookie/logout branches, configuration rejection branches, route traversal edges, and production step-up dependency-unavailable paths. Live runtime evidence remains unavailable because the sandbox has no Postgres, Redis, AuthService listener, browser-capable Playwright, Docker, or Podman.

The exact command results, evidence classification, remaining external blockers, DCO status, and no-push confirmation are recorded in `.pr2-evidence/final-validation.md`.
