# Tenancy and authorization posture decisions — 2026-11-14

**Title:** The nine remaining changes that move tenant-isolation or authorization posture, each stated as a decision the owner can approve or reject on its own.
**Base:** branch `feat/stage3-tenancy` at `6209155d`, plus the uncommitted stage-3 working tree.
**Owner:** Elshaday Mengesha (@Rick1330).
**Status:** Decision record, not an implementation record. Nothing here is implemented by the stage-3 pass that writes it, and no row in [`35-v1-remaining-gaps-staged-2026-11-13.md`](35-v1-remaining-gaps-staged-2026-11-13.md) is closed by this file. Each decision names the code as it stands today, the change proposed, what the change breaks, and the evidence that would prove it. Where a change is *not* safe to make, the record says so.

## 1. How to read this record

The stage-3 pass closed the six authorization rows in `35` §5.1 — the read surface and two destructive/management gates that were enforced by a single missing permission check. Every remaining tenancy row changes *posture*: which login a service holds, which credential admits a call, what a deletion guarantees, how a secret is stored, or how long a payload is retained. Those cannot be settled by a code change alone, because each one either weakens a claim or changes an operational contract. They are separated here so the owner can answer them one at a time.

Each section has the same shape:

- **True today** — the behaviour in the tree, with `file:line` for every claim.
- **Change** — the smallest change that alters the posture.
- **What it breaks** — the failure the change introduces if it is applied as stated.
- **Evidence needed** — the test or artifact that would prove the change works, not just compiles.
- **Recommendation** — one line.
- **Decision needed** — one line.

No number in this record is estimated. Counts are read from the tree and named with their source.

| ID | Decision | Rows | Posture question |
|---|---|---|---|
| D-S1 | Per-service DSNs and role pinning | P0-06, S08, GAP-002 | Does v1 claim database-enforced tenant isolation? |
| D-S2 | Worker enqueue org binding | S01 | What identity admits an internal enqueue? |
| D-S3 | Org deletion step-up | S02 | Must an unrecoverable action require a second factor? |
| D-S4 | Auth service-token scope | S04 | How many authorities may one static secret carry? |
| D-S5 | Erasure fan-out | S09, S10, P1-24 | Does "forget" mean every store or PostgreSQL only? |
| D-S6 | Secrets hygiene | S06, S07 | May a secret be reachable from a process listing? |
| D-S7 | MCP default environment | S11 | Does an unset environment relax trust? |
| D-S8 | Whole-body caps | P2-09 | Is request size bounded before parsing? |
| D-S9 | Retention | P1-21, P2-12, P2-15 | How long may tenant content stay in a non-tenant-scoped table? |

## 2. D-S1 — Per-service DSNs and role pinning (P0-06, S08, GAP-002)

**True today.** Every service the single-node profile starts connects to PostgreSQL as the `POSTGRES_USER` login, `ibex` (`infra/compose/v1-single-node/compose.yml`:26). The six DSNs — bootstrap `:121`, auth `:159`, proxy `:201`, API `:257`, memory `:303`, worker `:399` — all interpolate `${POSTGRES_USER:-ibex}`, and `ibex` is also the role every capability role is granted to (`infra/migrations/postgres/000004_rls.up.sql`:33 `GRANT ibex_app TO ibex`; `infra/migrations/postgres/000064_service_role_model.up.sql`:140 `GRANT ibex_service TO ibex`). The capability logins exist as `NOLOGIN`/`LOGIN` roles but are not the DSN identity: `ibex_runtime` (`infra/migrations/postgres/000064_service_role_model.up.sql`:43), `ibex_worker` (`infra/migrations/postgres/000064_service_role_model.up.sql`:49), `ibex_bootstrap` (`infra/migrations/postgres/000064_service_role_model.up.sql`:57), `ibex_purge` (`infra/migrations/postgres/000064_service_role_model.up.sql`:35). `ibex_runtime` and `ibex_worker` are members of `ibex_app` (`infra/migrations/postgres/000064_service_role_model.up.sql`:96) precisely so `SET LOCAL ROLE ibex_app` works without a DSN change.

The pinning is therefore uneven, and the S08 row understates it. Three stores pin the role inside the transaction: `packages/billing/store.go`:43, `packages/ratelimit/config_store.go`:68, `services/auth/internal/repository/tenant.go`:30. Three set only the org GUC and never pin: `packages/idempotency/ledger.go`:113, `packages/evidenceoutbox/store.go`:243, `packages/directive/store.go`:80. The relay is the one service that pins at connect time, through the PostgreSQL startup option `-c role=ibex_evidence_relay` (`services/relay/internal/bootstrap/wire.go`:96), and it verifies the resulting `current_user` at startup (`services/relay/internal/bootstrap/wire.go`:160).

RLS is inert on the unpinned paths because the connection is `ibex`: it is the `POSTGRES_USER` the image creates (`infra/compose/v1-single-node/compose.yml`:26), so it is a superuser, and RLS is not applied to a superuser at all. Table ownership alone would be cured by the `FORCE` each policy carries; the superuser attribute is not. Every policy also carries a service-account bypass, `OR current_setting('app.is_service_account', true) = 'true'` (`infra/migrations/postgres/000004_rls.up.sql`:10,22, and the same clause in the later migrations), which is the exact escape hatch stage-3 exit-gate item 1 says must be unavailable during the negative suite.

**Change.** Give each service its own capability login as its DSN identity — `ibex_runtime` for proxy and API, `ibex_worker` for the worker, `ibex_bootstrap` for bootstrap, `ibex_auth` for auth (`infra/migrations/postgres/000068_auth_login.up.sql`:31) — and add `SET LOCAL ROLE <capability>` to the stores that currently set only the GUC (`packages/idempotency/ledger.go`:113, `packages/evidenceoutbox/store.go`:243, `packages/directive/store.go`:80). Keep `GRANT … TO ibex` for migrations only. Flip `CONNECTION LIMIT 0` on the runtime logins to a configured limit.

What must be provisioned: a login role per service with a password held in the deployment secret store, membership of the matching capability role, `USAGE` on `ibex_core` and `ibex_billing` where read is claimed, and the exact table grants the service already needs. `infra/migrations/postgres/000064_service_role_model.up.sql` grants by column for the purge and relay roles; the runtime grants are wider and must be reviewed before a login is created against them.

**What it breaks.** A wrong DSN becomes a hard failure, not a silent cross-tenant read — and that is the point, but it is also the first thing that will break. `ibex_runtime` is declared `NOINHERIT` (`infra/migrations/postgres/000064_service_role_model.up.sql`:43), so a login that is a member of `ibex_app` but does not `SET ROLE` gets permission-denied rather than falling back to the superuser's rights. Every path that today resolves a table because it happens to run as `ibex` will fail the moment the DSN changes: any store that sets the GUC but not the role, any `SECURITY DEFINER` reader that assumed owner reach, and any migration helper that runs on the service DSN. The failure mode is fail-closed, which is correct, but it will surface as a 503 on read paths that are currently green. The alternative failure — a DSN pointed at the wrong org-capable role — is not fail-closed: a role with `BYPASSRLS` or ownership silently reads every tenant. The provisioning step must therefore assert `rolbypassrls = false` and non-ownership, not just connectivity.

**Evidence needed.** A test that connects on each capability DSN, inserts as org A, and asserts org B reads zero rows with the GUC set but no `SET ROLE` (proving the login itself is constrained); the same test with the GUC deliberately wrong returns zero rather than all rows; a startup assertion that `current_user` is the expected capability role, modelled on `services/relay/internal/bootstrap/wire.go`:160; and the cross-tenant negative suite in `35` §5 exit-gate item 1 run with `app.is_service_account` unset.

**Recommendation:** Approve. It is the only option that makes the isolation claim true rather than narrowed, and the fail-closed direction means a mistake surfaces in test rather than in a tenant's data.

**Decision needed:** Approve per-service capability logins plus `SET LOCAL ROLE` in the three unpinned stores, and authorise the secret-store and grant provisioning it requires — or record that v1 does not claim database-enforced isolation.

## 3. D-S2 — Worker enqueue org binding (S01)

**True today.** The worker's internal enqueue endpoint authenticates with one static bearer token and takes `org_id` from the JSON body. The check is `_authorize` (`services/worker/app/enqueue_http.py`:70-81): it compares the presented token to `settings.enqueue_api_token` with `hmac.compare_digest`, and nothing else. The body parser then reads `org_id`, `agent_id` and `session_id` from that same payload (`services/worker/app/enqueue_http.py`:141). The token is a single value in config (`services/worker/app/config.py`:153 names the port; the token field is `enqueue_api_token`, read at `services/worker/app/enqueue_http.py`:70). The only caller in the tree is the proxy (`services/proxy/internal/extractionenqueue/client.go`:20), which already holds the validated tenant in its request context and puts it in the body (`services/proxy/internal/extractionenqueue/client.go`:33-38).

The consequence: any holder of that one token can enqueue work for any `org_id` it names. The worker's own tenant-pinning readiness tests construct the token as a literal (`services/worker/tests/unit/test_enqueue_http_server.py`:110), so the test surface does not distinguish tenants either.

**Change — three options, with their blast radius.**

- **Per-org token.** The proxy selects a token by the org it already validated; the worker maps the token to an org and rejects a body mismatch. Blast radius: a secret per organisation must be minted, stored, delivered to both sides, and rotated when an org is deleted; the proxy needs a token lookup on the chat hot path; a missing token for a new org turns extraction into a silent drop because the client is fail-open by design (`services/proxy/internal/extractionenqueue/client.go`:1). It also multiplies the number of secrets that can leak.
- **Org claim in the token.** Replace the static comparison with a short-lived signed token minted by the proxy per request, carrying `org_id`, `agent_id` and `session_id`; the worker verifies the signature, expiry, and equality with the body. Blast radius: a shared signing key between proxy and worker (rotation, key id in the header), clock-skew and replay handling, and a new failure mode where a clock step drops extraction. It removes secret sprawl and binds every request to exactly one org. The proxy already has all three values in context, so no new lookup is needed.
- **Internal mTLS or workload identity.** Authenticate the call at the transport layer and accept the body's `org_id` only as a hint. Blast radius: certificate issuance and rotation for two workloads, a TLS listener on the worker's internal port, and the same fail-open client behaviour on a handshake error. mTLS proves *which service* called, not *which tenant*, so it does not fix S01 on its own — it must be paired with an org claim or a per-org authorisation.

**What it breaks.** Any option removes the "one token, any org" path, so a proxy that has not been upgraded, or a second caller added later without the claim, stops enqueuing. With the claim option, a proxy clock behind the worker rejects its own tokens; with the per-org option, an org created without a token enqueues nothing. The fail-open client means all three failures appear as missing extraction, not as an error to the caller, so the detection has to be a metric on enqueue rejections, not a user-visible failure.

**Evidence needed.** A negative test that presents a valid credential for org A with a body naming org B and asserts rejection (401/403, not a queued job); a test that the worker never enqueues when the claim and body disagree; a metric and alert on enqueue rejection count; and a revocation test for whichever credential is chosen (a rotated key or deleted token stops enqueues within the stated window).

**Recommendation:** The org claim in the token, minted by the proxy from the context it already holds; pair it with an enqueue-rejection metric so the fail-open client does not hide it.

**Decision needed:** Choose the org-claim token (recommended), per-org tokens, or mTLS-plus-claim, and state whether the enqueue stays fail-open or becomes fail-closed for extraction.

## 4. D-S3 — Org deletion step-up (S02)

**True today.** Deleting an organisation is an owner-role action gated on `ORG_SETTINGS_WRITE` and nothing else. The route is `services/api/app/routers/organizations.py`:68-71, using `RequireOwnerOrgSettings`; that dependency is `require_roles(OwnerRoles, required_permission=ORG_SETTINGS_WRITE)` (`services/api/app/authz.py`:111-114). `ORG_SETTINGS_WRITE` is not in the step-up mask (`packages/authclient/src/authclient/permissions.py`:63-74), so `requires_step_up` returns false for it (`:92-93`).

A detail that matters for any proposal: `require_roles` never consults the step-up mask at all (`services/api/app/authz.py`:79-100 — role check, permission check, return). Only `_assert_operator_bitmap` (`services/api/app/authz.py`:270-274) and `require_operator_permission` (`services/api/app/authz.py`:303-311) branch on `requires_step_up`. So **adding the bit to the mask alone does not make deletion require step-up**; it changes `requires_step_up` for every caller that consults it, and leaves the deletion route exactly as it is. The change has to move the route onto an async step-up dependency, modelled on `require_operator_legal_hold_manage` (`services/api/app/authz.py`:167-212).

**Change.** Route deletion through an owner-role dependency that calls `enforce_step_up` with a named action, and add `ORG_SETTINGS_WRITE` to the mask only if other routes that consult the mask should inherit the requirement. The two are separable and should be decided separately.

**What it breaks.** Owners without an enrolled TOTP factor cannot delete an organisation. The session-issuance path requires a TOTP state (`services/auth/internal/grpc/totp_session.go`:133-145) and `ConsumeStepUp` verifies the step-up token against expected subject, org, session, action and permission (`:253-266`), so a step-up-gated deletion is unavailable to any owner whose factor is lost, unenrolled, or locked out. That is the intended trade for an unrecoverable action, but it needs a documented recovery path — an owner who cannot step up cannot delete, and the only alternative is a database-level deletion done outside the product. If the mask is changed as well, any other route that consults `requires_step_up` for `ORG_SETTINGS_WRITE` starts demanding a factor it did not before; there is no such route today, so the mask change is currently inert and should be left out unless a route is moved onto it.

**Evidence needed.** A negative test that an owner session without a step-up proof gets a specific refusal and the organisation is not queued for deletion; a positive test that a step-up proof for a different action or a different org is refused; a test that an owner with no TOTP enrolment is refused and the refusal names the recovery step; and a runbook section that states who can recover a lost factor.

**Recommendation:** Approve moving deletion onto the async step-up dependency and leave the mask unchanged, with the lost-factor recovery documented in the same change.

**Decision needed:** Require step-up for org deletion, yes or no — and if yes, name the recovery path for an owner who has lost the factor.

## 5. D-S4 — Auth service-token scope (S04)

**True today.** One shared static secret admits four distinct authorities. `serviceLifecycleMethods` lists `ValidateOperatorSession`, `RevokeOperatorSession` and `ConsumeStepUp` (`services/auth/internal/grpc/authz.go`:28-33), and `isServiceLifecycleMethod` adds `IssueOperatorSession` to the same set (`services/auth/internal/grpc/authz.go`:106-111). The interceptor admits any of the four when the presented value equals the configured token, compared in constant time (`services/auth/internal/grpc/authz.go`:62-90 and `services/auth/internal/grpc/authz.go`:113-125); only `ValidateToken` bypasses the check entirely (`services/auth/internal/grpc/authz.go`:64-66).

Precision on "issuance is not org-bound": the session itself *is* org-bound. `issueFromCaller` mints from the caller PAT's org (`services/auth/internal/grpc/totp_session.go`:295-313), and `issueFromRefresh` mints from the refresh token's claims (`:275-286`). The gap is the credential, not the session: one secret is valid for every org's refresh token, and the same secret can revoke any org's session and consume any org's step-up proof, because the interceptor does not compare the credential to the org it acts on.

**Change.** Split the authority. At minimum, separate the session-lifecycle credential (issue/validate/revoke) from the step-up-consumption credential, so a leaked issuance secret cannot silently approve a step-up. Bind issuance: the service credential presented for `IssueOperatorSession` carries or is checked against the org of the refresh token it presents. Prefer per-purpose secrets with distinct config keys over one `auth_service_token` reused four ways.

**What it breaks.** Two secrets replace one, so every deployment that sets `IBEX_AUTH_SERVICE_TOKEN` (aliased `IBEX_API_AUTH_SERVICE_TOKEN`, `services/api/app/config.py`:44) needs a second value and a rollout ordering: the auth service must accept the new secret before the API presents it, or login and refresh fail. A per-org binding needs an org lookup before issuance, which adds a dependency to the login path. The step-up path is the one to split first, because a wrong step-up secret fails closed at the action, whereas a wrong issuance secret fails closed at login — visible and recoverable, unlike a mis-scoped approval.

**Evidence needed.** A test that the issuance secret is refused for `ConsumeStepUp`, and the step-up secret refused for `IssueOperatorSession`; a test that a credential scoped to org A is refused when the refresh token belongs to org B; a rotation test that both secrets roll with the documented overlap; and a negative test that `ValidateToken`'s unconditional bypass (`services/auth/internal/grpc/authz.go`:64-66) is intentional and does not extend to any state-changing method.

**Recommendation:** Approve the split, step-up separated from session lifecycle first, with org binding on issuance as a second, independently releasable step.

**Decision needed:** Approve splitting the service credential by authority and binding issuance to the refresh token's org — and confirm the fail-closed rollout order.

## 6. D-S5 — Erasure fan-out (S09, S10, P1-24)

**True today.** A memory forget erases PostgreSQL child rows and scrubs the idempotent create response, and stops there. The erase statements in `services/memory/app/lifecycle.py`:145-177 delete `memory_labels`, `memory_feedback`, `memory_relationships`, `memory_conflict_escalations` and update `idempotency_ledger.response_payload` to the erased marker (`services/memory/app/lifecycle.py`:168-176). There is no S3, ClickHouse or evidence-table path in that module. Capture archives are written by the worker under `{org_id}/capture/{kind}/{object_id}.json` (`services/worker/app/tasks/capture_redaction.py`:271) and are not addressed by a memory forget. Post-commit cache invalidation is best-effort: `invalidate_forgotten_memory` logs and returns (`services/memory/app/routers/memory_write_support.py`:541-559) — the forget has already committed, so a failed invalidation leaves a hot cache entry readable.

Whole-organisation deletion does fan out — the worker's deletion stages reach ClickHouse, Redis and object storage (`services/worker/app/tasks/org_deletion_stores.py`:140,196) — which proves the capability exists and is simply not wired to a per-memory forget. That asymmetry is the defect: erasure is complete at org granularity and partial at memory granularity, and the product claims the second.

**Change.** A complete per-memory erasure needs: a durable fan-out record written in the forget transaction (an outbox row, generated in the same commit as the tombstone); a worker consumer that deletes the capture objects by the `{org_id}/capture/**` prefix keyed on the memory's events, mutates or deletes the ClickHouse event rows and evidence rows, and writes a per-store receipt; cache invalidation retried from the same record with a bounded schedule and a receipt, not logged; and a read-path guard so a memory whose fan-out has not completed is not served from cache or a replica. Cost: two new durable artifacts (fan-out rows and per-store receipts), a worker task with idempotent per-store deletes, a ClickHouse mutation or lightweight delete that must be proven absent via the count-then-wait pattern already used by org deletion (`services/worker/app/tasks/org_deletion_stores.py`:115-137), and a retention interaction with D-S9 because the receipt must outlive the content.

**What it breaks.** Forget stops being a single-transaction operation from the caller's point of view. If the route waits for fan-out, forget latency becomes the slowest store's latency and a ClickHouse or S3 outage makes forget return 5xx after the tombstone has committed — a partial state the caller cannot distinguish from "nothing happened". If it does not wait, "forget" becomes eventually complete and the claim must say so, with a stated completion deadline and a way to read the receipts. The object-store deletion also needs an auditable trace, because a bug that deletes by a broader prefix than intended is unrecoverable.

**Evidence needed.** A forget of a memory that has a capture archive, a ClickHouse event and an evidence row, followed by an assertion of absence in all three plus PostgreSQL; a test that a failed cache invalidation is retried and receipted rather than logged; a test that a forget has not yet fanned out is not served stale; and a restore-replay test, extending the PostgreSQL-only one in `infra/migrations/postgres/restore_replay_integration_test.go`, that a restore does not resurrect the erased content.

**Recommendation:** Approve asynchronous fan-out with durable receipts and a stated completion deadline, and change the claim from "forget erases" to "forget tombstones synchronously and completes erasure within the deadline, provable by receipt" until the fan-out is proven.

**Decision needed:** Approve an asynchronous receipted erasure fan-out with a named deadline, or narrow the erasure claim to PostgreSQL plus the idempotency record for v1.

## 7. D-S6 — Secrets hygiene (S06, S07)

**True today.** The Redis password is on the container's argument vector: `command: ["redis-server", "--requirepass", "${REDIS_PASSWORD}"]` (`infra/compose/v1-single-node/compose.yml`:45). The healthcheck passes it again as `-a "$$REDIS_PASSWORD"` (`:49`). Both are readable from `docker inspect`, from `/proc/<pid>/cmdline` on the host, and from any process-listing scrape. Three API secrets are typed as plain `str`: `auth_service_token` (`services/api/app/config.py`:44), `jwt_hmac_secret` (`:111`), `dashboard_csrf_secret` (`:145`). A plain `str` field is included in `repr`, in Pydantic's error context, and in any structured log that serialises settings.

**Change.** Move the Redis password out of argv: mount a 0400 `redis.conf` containing `requirepass` (or an ACL file) and start `redis-server /etc/redis/redis.conf`; healthcheck with `REDISCLI_AUTH` from the container environment rather than `-a` on the command line. Convert the three API fields to a secret type (`SecretStr` or the repo's `ibexconfig.Secret` wrapper, which the Go config already uses) and read them through the accessor at every call site.

**What it breaks.** A config file is one more artifact for `make v1-secrets` to render and permission, and a mistake there means Redis starts with no password or fails to start. `SecretStr` changes the type of three fields, so every use that treats them as strings must switch to `.get_secret_value()`, and every test that builds settings from a literal must wrap it. Any code that logs the whole settings object will now print `**********` — which is the point, but it also means a debugging aid disappears and must be replaced by an explicit, redacted field. The Redis change does not fully remove the secret from the environment: it moves it from argv to a file and to `REDISCLI_AUTH`; a process-listing test must assert the argv no longer carries it, not that the secret is unreachable everywhere.

**Evidence needed.** A test or a scripted check that reads `/proc/<redis-pid>/cmdline` (or `docker inspect` output) and asserts the password is absent; a test that `repr(settings)` and the structured log line for startup contain no secret value; a secrets-scan run that still passes; and a startup test that a missing Redis config file fails closed rather than starting without auth.

**Recommendation:** Approve both, since a process-listing test is already required by stage-3 exit-gate item 5 and neither change alters a product claim.

**Decision needed:** Approve moving the Redis password out of argv and typing the three API secrets as secret values; confirm `make v1-secrets` owns the new Redis config file.

## 8. D-S7 — MCP default environment (S11)

**True today.** Both MCP servers default `IBEX_ENV` to `development` when it is unset. Memory: `services/mcp-memory/app/config.py`:31-33 (`env: str = Field(default="development", …)`); operator: `services/mcp-operator/app/config.py`:35. The default is load-bearing for transport trust: memory passes `allow_test_hosts=cfg.env != "production"` (`services/mcp-memory/app/main.py`:79), so an unset environment enables the test-host allow-list, and only `production` forbids the stdio transport (`services/mcp-memory/app/config.py`:127). The single-node profile does not launch either MCP server — there is no MCP service in `infra/compose/v1-single-node/compose.yml` — so this is a deployment-configuration risk in whatever profile does, not a defect visible in the supported profile's Compose file.

**Change.** Make the environment explicit: either default to `production`, or require `IBEX_ENV` (or `IBEX_MCP_ENV`) to be set and fail startup when it is absent. Keep the alias, and make the failure message name both variables.

**What it breaks.** Every local invocation and every test that constructs `Settings()` without the variable starts failing. The fix is environmental (`IBEX_ENV=development` in the dev path and in test fixtures), but it is a fleet-wide edit across tests and any developer machine that relies on the default. A deployment that today runs an MCP server with no `IBEX_ENV` starts refusing to start after the change — correct, but it is a breaking startup change that must be in the upgrade notes. Defaulting to `production` instead of failing closed avoids the hard break but silently changes behaviour for a dev machine that forgot the variable (test hosts stop working) with no error, which is harder to diagnose than a refusal.

**Evidence needed.** A test that an unset environment refuses to start (or resolves to `production`, depending on the chosen option) and that the refusal names the variable; a test that `IBEX_ENV=development` still allows test hosts; a test that `IBEX_ENV=production` refuses stdio; and a line in the upgrade guide for whichever option is chosen.

**Recommendation:** Require the variable and fail startup, rather than defaulting to `production`: an absent value is a configuration error, and a refusal is easier to diagnose than a behavioural change.

**Decision needed:** Require `IBEX_ENV` and fail closed, or default to `production` — and confirm the upgrade-note wording.

## 9. D-S8 — Whole-body caps (P2-09)

**True today.** None of the three HTTP services caps request body size before parsing. The API registers six middleware entries (`services/api/app/main.py`:228-233, one of them the conditional deprecation emitter) and none is a size guard; the memory service registers two (`services/memory/app/main.py`:106-107); the middleware package holds five middleware modules and an `__init__`, none a size limiter (`services/api/app/middleware/`). Per-field bounds exist and are real — `services/memory/app/schemas/limits.py`:8-16 caps labels, tags, metadata keys, metadata bytes and nesting depth — but they are applied after the body has been read and parsed, so a large or deeply nested document is decoded before it is rejected. The memory limit reader does bound `MAX_BEARER_TOKEN_BYTES` (`services/memory/app/schemas/limits.py`:11) but not the request entity.

**Change.** An ASGI middleware in each service, added outermost enough to run before body parsing, that rejects a declared `Content-Length` above a per-service limit and counts a chunked body as it streams, aborting above the same limit with a stable 413 envelope. Declare the limit per service and per route family, and add it to the error contract so it is a documented rejection rather than a framework default.

**What it breaks.** Any legitimate payload above the chosen limit — a large batch memory write, a bulk search request, a long transcript in an enqueue — is rejected. The limit therefore has to be set above the largest supported payload and the supported maximum stated in the API reference, or a client that works today starts getting 413. Chunked uploads that a proxy holds open need the counting implementation, not just a header check, or the cap is bypassable by omitting `Content-Length`. The wrapper also has to preserve the request stream for the route, which is a common source of subtle body-consumption bugs.

**Evidence needed.** Per-service tests that a body just under the limit succeeds and one just over returns the documented 413 envelope; a chunked-body test with no `Content-Length` that is still rejected; a test that the 413 carries the standard error shape and a request id; and a recorded largest-supported-payload statement matching the configured limit.

**Recommendation:** Approve, with the limit derived from the largest documented payload plus headroom, and the number published in the API reference.

**Decision needed:** Approve per-service whole-body caps and name the supported maximum payload per service.

## 10. D-S9 — Retention (P1-21, P2-12, P2-15)

**True today.** Three tables keep tenant content without a tenant scope or a retention bound.

- `failed_tasks` has no RLS and no prune. The migration says so in its first line — "No RLS (operator forensics; service-account inserts)" (`infra/migrations/postgres/000021_create_failed_tasks.up.sql`:1-2) — and it stores `args`, `kwargs` and a full `traceback` (`infra/migrations/postgres/000021_create_failed_tasks.up.sql`:8-12). The worker's own documentation repeats the fact (`services/worker/app/db.py`:148). There is no delete path: the repository only inserts (`services/worker/app/repositories/failed_tasks.py`:18).
- `usage_facts` in ClickHouse has no TTL by decision, not by omission: the migration states "No TTL: billing/financial retention (SECURITY.md section 11). Ops purge policy is explicit" (`infra/migrations/clickhouse/000005_usage_facts.up.sql`:2), and the table is a plain `MergeTree` (`infra/migrations/clickhouse/000005_usage_facts.up.sql`:30). Retention here is a finance decision, and `35` §4.2 records it as such (P2-12).
- `idempotency_ledger` keeps finalized payloads indefinitely (`infra/migrations/postgres/000043_idempotency_ledger.up.sql`:2-18, with `response_payload BYTEA` at `infra/migrations/postgres/000043_idempotency_ledger.up.sql`:10 and only a lease index at `infra/migrations/postgres/000043_idempotency_ledger.up.sql`:19. `budget_reservations` is deliberately never deleted — the migration says rows "are never deleted by the application roles; release and expire keep the history" (`infra/migrations/postgres/000046_budget_reservations.up.sql`:1-3) — which is an accounting requirement, not a leak, but it is unbounded growth all the same.

**Change.** Three separable decisions, and they should not be bundled:

- For `failed_tasks`: add a prune policy with a stated window, and either add RLS with an org policy or reduce the stored payload to the fields needed for forensics (task name, exception type, and a redacted message) rather than `args`/`kwargs`/`traceback`. The second is the smaller change and removes the content exposure without a retention window.
- For `usage_facts`: a TTL or a scheduled purge, once finance states the retention period. No engineering choice can substitute for that number.
- For `idempotency_ledger` and `budget_reservations`: a reaper for ledger rows past a stated replay window, keeping the accounting history in `budget_reservations` and pruning the payload only. The ledger's `response_payload` is the field that carries tenant content; the row itself is the replay guard.

**What it breaks.** A prune on `failed_tasks` removes forensic rows an operator may be relying on during an incident, so the window has to be long enough to cover a triage cycle and the prune has to be visible in a metric. Redacting `args`/`kwargs` removes the reproduction detail that makes a dead-letter row useful; the trade is explicit. A TTL on `usage_facts` changes billing reproducibility, which is why it is finance's call. Pruning finalized idempotency rows means a replay after the window re-executes the write instead of returning the stored response — acceptable only if the window exceeds every client's retry horizon, and it must be stated in the idempotency contract.

**Evidence needed.** For each change: a test that a row older than the window is pruned and a row inside it survives; a metric and alert on prune count and on the oldest surviving row's age; a test that a replay inside the window still returns the stored response after the prune job runs; and, for `failed_tasks`, a test that a redacted row contains no `args`, `kwargs` or `traceback` content. For `usage_facts`, a written retention period from finance is the evidence, not a test.

**Recommendation:** Approve redaction of `failed_tasks` payloads plus a prune window, and a reaper with a published replay window for the ledger; leave `usage_facts` open until finance states the period, and do not guess one.

**Decision needed:** Name the `failed_tasks` retention window and whether its payload is redacted or retained under RLS; name the ledger replay window; obtain the `usage_facts` retention period from finance or record that it has none.

## 11. What approval does not do

Approving a decision here does not close its row in `35`. Each row closes on a merged change with the evidence named above, and the evidence for D-S1, D-S2, D-S4 and D-S5 includes the cross-tenant negative suite that requires a two-tenant environment. No ledger value moves, no review date moves, and no availability or isolation claim is promoted by this record.
