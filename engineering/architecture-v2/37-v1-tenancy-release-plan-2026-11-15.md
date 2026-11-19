# v1 tenancy release plan — 2026-11-15

**Title:** The ten owner decisions taken on 2026-11-15, and the four stages that turn "multi-tenant is a v1 claim" into evidence.
**Base:** `main` at `d64eddbb` (2026-11-15), re-opened on 2026-11-15 after the stage-1 flip landed in the working tree. Every `file:line` below resolves against that tree; §4.1 records each citation the flip moved.
**Audience:** The operator. This is the document to read before sequencing any remaining v1 work.
**Status:** Plan. It records decisions already taken, orders the work those decisions create, and states what ends each block. It closes no row in [`35-v1-remaining-gaps-staged-2026-11-13.md`](35-v1-remaining-gaps-staged-2026-11-13.md) and moves no value in [`00-status-and-evidence.md`](00-status-and-evidence.md); a row closes on a merged change with its own evidence. It promotes no status: `shipped-local`, `provisional` and `design-intent` keep the meanings `00` gives them (`00-status-and-evidence.md`:97-103).

**Reads with:** `35` (the 84 open rows and their blockers), [`36-tenancy-posture-decisions-2026-11-14.md`](36-tenancy-posture-decisions-2026-11-14.md) (the nine posture questions, D-S1…D-S9), [`31-v1-release-plan-2026-11-09.md`](31-v1-release-plan-2026-11-09.md) (the W-wave map), `00` (the claim vocabulary).

---

## 1. Decisions taken (2026-11-15)

Ten decisions are settled. They are recorded here because each one either creates release work or removes a row from the release.

| # | Decision | Call | Reason | What it unblocks |
|---|---|---|---|---|
| 1 | Multi-tenant is a v1 claim | **Claimed.** One install, many orgs, isolation enforced by the database. | Owner decision. A product that provisions orgs and calls itself a memory platform for teams cannot record "one tenant per install" as a limitation and still be the product in the README. | Turns `P0-06`, `S01`, `S04`, `S05`, `S08`, `S09`, `S10`, `R05` from recorded limitations into release work. Makes stage 1 mandatory. |
| 2 | Console 1.0 scope | **Login + mutations.** Not login + declared read-only. | A multi-tenant operator must be able to provision and manage orgs; a read-only BFF contradicts decision 1. Today every operator data route is a read and none writes an operator record: 18 `*.get.ts` under `services/console/server/api/operator`; the three `.post.ts` session routes (login, logout, refresh) are the only cookie actions the browser initiates, and a `401` read can still rotate the expired session server-side. | `P0-05`, `P1-40`, `D02`, `P2-05` become release work. Sets stage 4's size. |
| 3 | Off-host backup | **Not in v1.** | The only repository in the supported profile is pgBackRest over S3 pointed at the in-profile MinIO (`infra/backup/pgbackrest/pgbackrest.conf.example`:6-9), whose data is the local named volume `objectstore-data` (`infra/compose/v1-single-node/compose.yml`:125-126, declared `:710`) on the same host as `postgres-data` (`:68`, declared `:707`). Calling that recovery would be false. | RPO/RTO stay unsigned; `D-D` (`35`:438) becomes a post-v1 item. `P0-09`, `P0-11` are reclassified, not closed. |
| 4 | `durable-before-ack` | **Not claimed.** The ledger states post-response, best-effort. | The finalizer is post-response and the relay is default-off (`00-status-and-evidence.md`:63-65); ADR-0097 already excludes a response-bound acknowledgement from 1.0 (`engineering/adr/0097-v1-supported-profile.md`:211). | `D4` and `D11` close by recording the boundary rather than by building a synchronous acknowledgement. |
| 5 | Benchmark v2 number | **None published for v1.** | The published artifacts carry no provenance: `python3 benchmarks/scripts/check_reproducibility.py` at this commit reports 146 unrecorded runs across 5 artifacts, and the ranking baseline has no `sha`, gold-set hash or seed. | `P1-26`, `P1-27`, `P1-33`, `P1-38`, `P1-39` leave v1. `P0-20`/`D03` narrow to "a published number must have provenance before it is cited". |
| 6 | `S13` forget permission | **Stays write-gated, recorded.** | No role bitmap grants `MEMORY_DELETE` (`packages/authclient/src/authclient/permissions.py`:7 vs `:38-60` and `:76-81`), so gating forget on it made forgetting impossible for every real token. The route is gated on `require_memory_write` (`services/memory/app/routers/memories.py`:95-97). | `S13` closes by recording the gate and the reason, not by granting a bit that no role carries. |
| 7 | `O04` Redis | **Stop calling Redis ephemeral.** It is the Celery broker. | Redis is the broker (`infra/compose/v1-single-node/compose.yml`:91) and its loss 503s chat; a recovery record that calls it disposable cannot be true at the same time. | `O04` closes by correcting the recovery text. Removes the last "Redis is optional" claim. |
| 8 | Support window for 1.0 | **None.** Stated, not implied. | With off-host recovery out (decision 3) and no signed RPO/RTO, a support promise would be unsupported by the release's own evidence. | `P1-46` closes by stating the absence in the upgrade guide rather than by signing a window. |
| 9 | Helm chart | **Retired.** | ADR-0097 §10 already excludes it (`engineering/adr/0097-v1-supported-profile.md`:209). A chart with sentinel digests is not an artifact anyone can deploy. | `P2-24` and `D-B` (`35`:318) need no work; the guard is not wired because the chart is not shipped. |
| 10 | `S06` / `S07` / `S11` | **Fixed, not recorded.** | A secret on the container argv (`compose.yml`:91, and again in the healthcheck `:95`) and three plain-`str` API secrets are defects with known fixes, not limitations to carry. | They are ordinary work in stage 3; no ledger row needs to describe them as a limitation. |

**What each decision closes or reclassifies, and the ledger line it moves.** Row IDs are from `35`; the register tables are §3.2 (`35`:84-92), §4.2 (`35`:144-159), §5.2 (`35`:197-236) and §6.2 (`35`:266-300).

| # | Register rows | Ledger line that must change |
|---|---|---|
| 1 | `P0-06`, `S08`, `S01`, `S05`, `S04` (`35`:201,230,224,227,226) become release work; `P0-21`, `P2-07` (`35`:202,213) are the proof; `S09`, `S10`, `R05` (`35`:231,232,158) inherit it. | `v1-single-node deployment profile` (`00`:39): when this plan was written it read "every DSN still points at the owner login" and "not multi-user, not … cross-tenant … one host and one tenant". The DSN half has since moved to the capability logins (§3.6); the isolation half is still unearned until `P0-21` and `P2-07` land. `Memory substrate` (`00`:27): "not proof of … production isolation". Both must be re-earned, not reworded. |
| 2 | `P0-05`, `P1-40`, `D02`, `P2-05` (`35`:271,285,298,291). | `Operator Console core-tier live reads` (`00`:36): the "No login, mutation, org-switching" clause. `preview and platform tier` (`00`:37): the two core `preview` surfaces. |
| 3 | `P0-09`, `P0-11` reclassified post-v1 (`35`:148,150); `GAP-011`, `P0-19` (`35`:154,151) keep their in-profile half only. | `Production operations, HA, recovery, and release gates` (`00`:40): "No … passing RPO target" becomes "no RPO/RTO is claimed; the repository is on the same host". |
| 4 | `D4`, `D11` close by recording (`35`:156,157). | `00`:63-65 states the post-response finalizer and the default-off relay; the rows for `evidence-envelope.v1` (`00`:75), `evidence-relay-sink.v1` (`00`:76), relay daemon (`00`:81) and the session producer (`00`:82) must drop the "open decision" framing and state it as a v1 limitation. |
| 5 | `P1-26`, `P1-27`, `P1-33`, `P1-38`, `P1-39` reclassified post-v1 (`35`:280-284). `P0-20`, `D03` (`35`:273,299) narrow. | `Ranking-quality benchmarks` (`00`:30) already says no v2 number is published; it must also say no v2 number is *claimed*. `Proxy overhead SLO and benchmark gate` (`00`:25) and `GAP-004` (`00`:78) keep "target, not measured". |
| 6 | `S13` (`35`:234) closes by record. | `Memory substrate` (`00`:27) limitations gain the write-gated forget. |
| 7 | `O04` (`35`:155). | `Extraction workers` (`00`:31): queue durability is not certified *and* Redis is a required broker, not a disposable cache. |
| 8 | `P1-46` (`35`:90) closes by record. | `Production operations …` (`00`:40) states the absence of a support window in the same sentence as the absence of an RPO. |
| 9 | `P2-24`, `D-B` (`35`:318,98) need no work. | No ledger row: the ledger has no Helm row, and ADR-0097 §10 is the record (`engineering/adr/0097-v1-supported-profile.md`:209). |
| 10 | `S06`, `S07`, `S11` (`35`:228,229,233) close on merged changes. | No ledger row cites them; they are register rows only. |

---

## 2. The four stages

| Stage | Theme | Why it is in that position | Exit evidence |
|---|---|---|---|
| **1 — Tenancy spine** | Capability DSNs, role pinning, token/org binding, cross-tenant proof. | It is the only stage whose failure is a silent cross-tenant read. Under the owner login a missing role pin is invisible; under a capability login the same bug is `42501`. Every later stage writes rows through these stores, so a later stage would bank its evidence under an unpinned login. | The cross-tenant negative suite green with `app.is_service_account` unset, at route level, on the proxy/chat path and in a two-tenant browser journey; a startup assertion that `current_user` is the expected capability role; a test that a GUC-only transaction under `ibex_runtime` fails `42501`. |
| **2 — Destructive paths** | Erasure fan-out, deletion step-up, retention, committed PITR evidence, upgrade rehearsal. | Data loss and resurrection are the failures a release cannot repair after the tag. It needs stage 1 because the fan-out writes new durable rows through the same stores, and it needs the pinned login so the restore is taken of the cluster that ships. | A forget with a capture archive, a ClickHouse event and an evidence row is absent in all four stores, receipted, within a stated deadline; org delete refuses without a step-up proof; every retention window named and enforced; a **committed** drill report with a PITR mechanism; a `v0.1.9→head` rehearsal and an up→down→up cycle. |
| **3 — Release integrity** | Signed tag and token, manifest/SBOM/provenance, production-profile start, benchmark provenance, claim-set checker, branch protection, `v1-smoke` in CI. | It certifies the artifact, so it can only be honest after 1 and 2. Turning these gates on earlier certifies a product whose isolation and erasure are unproven, which is worse than leaving them off. | A release cut by the pipeline from a signed tag with a signed, schema-validated manifest and per-image SBOMs that verify; the profile serves one authenticated chat request on `IBEX_ENV=production` plus two negatives; `make v1-smoke` runs in CI; all nine declared required contexts enforced; the claims checker covers `app/components/**` and `public/benchmarks/*.json`. |
| **4 — Operator product** | Console mutations and tenant provisioning, token accounting, pagination, SSE envelope, package pruning, `mcp_runtime` tests. | It is last because it consumes the spine: provisioning an org is the operation the cross-tenant suite proves, and an org-delete button on an unproven step-up path is a footgun. It is also the only stage a user sees, so it must not be built on a moving identity model. | A clean-browser login → live page → refresh → logout with no fixture cookie; one mutation that provisions an org and one that changes operator state; paginated capture policies and legal holds; token counts that include tool-schema and formatter overhead; an SSE error envelope carrying `request_id`. |

### 2.1 Stage 1 — scope by row

`P0-06` (no service DSN on its capability login — the DSNs are flipped and asserted now, §3.6), `S08` (six Go stores set the org GUC and never pin — they now pin through `packages/pgtenant`), `S01` (worker enqueue takes `org_id` from the body behind one static token — now a signed claim plus a body-equality check), `S05` (context calls memory with one static PAT — now `X-Ibex-Org-Id` plus a 403 on mismatch), `S04` (one secret for four authorities — now split into lifecycle and issue, with an org assertion), `GAP-002` (authority propagation), `P0-21` and `P2-07` (the two-tenant journeys), `P2-22` (login rate limit), `S14` (exception-message log rule), `S13` (recorded), `D6` (signed or recorded). **12 rows.** The parentheticals record where each row stands; a row still closes only on merged evidence, and the two-tenant journeys remain the proof both `P0-06` and `S08` lack.

### 2.2 Stage 2 — scope by row

`S02` (org deletion step-up), `S09` and `S10` (erasure fan-out and receipted cache invalidation), `P1-24` (object-store purge), `P1-21`, `P2-12`, `P2-15` (retention: `failed_tasks`, `usage_facts`, ledger rows), `GAP-007` (typed lifecycle), `GAP-005` (isolation/deletion/evidence end to end — closes last here), `P0-10` (committed PITR evidence), `R05` (post-restore erasure), `P1-22`, `P1-23`, `P2-06`, `P2-14` (upgrade rehearsal, and the irreversible families named in the release note), `P1-17` and `S04`'s **split half** (credential lifecycle and rotation), `D4`, `D11` (recorded), `O04` (recorded). Reclassified, not closed: `P0-09`, `P0-11` (post-v1 per decision 3), `P0-19` (paging destination is operator-supplied once no support window is claimed), `GAP-011` (in-profile half only). **23 rows.**

### 2.3 Stage 3 — scope by row

`P0-15`, `P1-07`, `P1-08`, `P1-09`, `P1-10` (signed tag, signed manifest, SBOMs, reproducible build), `P0-22` (production-profile start), `P2-13` (deployed seed cannot mint an owner credential), `P1-15` (auth TLS negative test), `P1-16` (OTLP cleartext), `P1-14` (`mcp-memory` host allow-list), `P1-18`, `P2-25` (waivers and Dependabot coverage), `P1-04` (dependency matrix), `P1-50` (relay image, `mcp-operator` publish), `P0-20`, `D03`, `P1-52`, `GAP-004` (provenance for anything cited; the p99 stays a target), `R02`, `GAP-001` (claims checker and its owner), `P1-46` (recorded absence), `P1-25`, `P1-11` (required checks), `W7.5` (`v1-smoke` in CI), `W6.3` (SLOs ratified or recorded), `P1-47` (soak record), `S06`, `S07`, `S11` (secret hygiene). **29 rows.**

### 2.4 Stage 4 — scope by row

`P0-04` (clean-browser journey), `P0-05` (mutations), `D02` (README reaches the supported profile), `P2-05` (two core surfaces still `preview`), `P1-40` (tenant provisioning route), `P1-41` (Console schemas duplicated from OpenAPI), `P1-42`, `P2-09`, `P2-19` (HTTP contract: error envelope, whole-body caps, SSE envelope), `P2-16`, `P2-17`, `GAP-006` (token accounting), `P2-18` (pagination), `P2-01` (no-op worker skeletons), `P2-02` (package pruning), `GAP-009` (MCP/operator boundary). Plus one item that is not a register row: `packages/mcp_runtime` carries the middleware, rate limit and metrics that `mcp-memory` imports (`services/mcp-memory/app/middleware.py`:10) and has no tests of its own. **15 rows + 1 package.** `P2-09` (whole-body caps) sits here with the HTTP contract work rather than in stage 1 because it is a resource-exhaustion guard, not a confidentiality control; if the operator reads it as a security gate, it moves to stage 1 and stage 1 grows by one task.

### 2.5 Not in v1 — reclassified, recorded

`P1-26`, `P1-27`, `P1-33`, `P1-38`, `P1-39` (`35`:280-284) leave v1 under decision 5. They are not deleted: each stays in `35` §6.2 with the reason "no v2 number is published", and `00`:30 must say so. **5 rows.**

**Arithmetic.** 84 open rows at this base (`35`:382) = stage 1 12 + stage 2 23 + stage 3 29 + stage 4 15 + post-v1 5.

### 2.6 The 14 owner decisions, placed

Ten are taken (§1). Four are still needed, and each is an entry condition for the stage that needs it.

| Decision | Stage | Status | Why there |
|---|---|---|---|
| 1 Multi-tenant claim | 1 | Taken | It is what makes stage 1 work required rather than optional. |
| 2 Console scope | 4 | Taken | It sets stage 4's size. |
| 3 Off-host backup | 2 | Taken | It reclassifies stage 2's recovery rows. |
| 4 `durable-before-ack` | 2 | Taken | The evidence-plane boundary is decided with the erasure/retention work. |
| 5 No benchmark v2 | 3 | Taken | The claims checker is what makes "not published" enforceable. |
| 6 `S13` recorded | 1 | Taken | It is an authorization gate decision. |
| 7 `O04` Redis | 2 | Taken | It is a recovery-record correction. |
| 8 No support window | 3 | Taken | It is stated where the release notes are produced. |
| 9 Helm retired | 3 | Taken | No work; the exclusion is a release-note line. |
| 10 `S06`/`S07`/`S11` fixed | 3 | Taken | They are properties of the shipped profile. |
| **D-A** release credential and tag key | 3 | **Open** | Stage 3 cannot cut a signed tag without it. |
| **D-S3 / `S02`** deletion step-up, bearer retained | 2 | **Open** | The route shape decides whether an owner PAT can still delete. |
| **D6** `PrincipalContext` signed or recorded | 1 | **Open** | The claim cited by context assembly is decided with the spine. |
| **D-S9** retention windows | 2 | **Open** | No engineering choice can substitute for the numbers. |

`D-B`, `D-C` and `D-D` are answered by decisions 9, 2 and 3 respectively and are not counted again.

---

## 3. Stage 1 — the tenancy spine

The design is settled. This section records it; it does not reopen it.

### 3.1 Target identity model

| Workload | Login | Membership | Evidence |
|---|---|---|---|
| proxy, api, memory | `ibex_runtime` | `ibex_app` | `infra/migrations/postgres/000064_service_role_model.up.sql`:43,96 |
| worker | `ibex_worker` | `ibex_app`, `ibex_purge` | `000064_service_role_model.up.sql`:49,96,139 |
| auth | `ibex_auth` | `ibex_app` | `infra/migrations/postgres/000068_auth_login.up.sql`:31; `infra/migrations/postgres/provision.go`:67-71 |
| migrate, provision | owner login `ibex` | — | see below |
| bootstrap | `ibex_bootstrap` | none — reaches tables only through `SECURITY DEFINER` functions | `infra/migrations/postgres/provision.go`:61-65; `infra/migrations/postgres/000069_bootstrap_definers.up.sql`:7-14 |

Context is absent from the table on purpose: it holds no database DSN in the profile at all — it reaches memory over HTTP and Redis (`infra/compose/v1-single-node/compose.yml`:589-601), so its tenant binding is `S05`, not a login.

`ibex_runtime`, `ibex_worker`, `ibex_bootstrap` and `ibex_auth` are the four provision targets (`infra/migrations/postgres/provision.go`:47-71); each is created `NOINHERIT` with `CONNECTION LIMIT 0` (`000064`:43) and activated only by `provision`.

**Why bootstrap is on `ibex_bootstrap`, not the owner.** The login holds no memberships at all (`provision.go`:61-65) and reaches the database only through `SECURITY DEFINER` functions granted to it (`infra/migrations/postgres/000069_bootstrap_definers.up.sql`:7-14,615). The one-shot bootstrap service therefore connects as `ibex_bootstrap` (`infra/compose/v1-single-node/compose.yml`:268). The definer path is the reason the owner credential is not needed; `ibex_bootstrap` is granted `EXECUTE` only, with no table privilege of its own.

**What still needs the owner credential, and why.** `migrate` and `provision` are the only workloads left on it. `provision` sends exactly one statement per target, `ALTER ROLE … CONNECTION LIMIT -1 PASSWORD …` (`infra/migrations/postgres/provision.go`:211-213, statement at `:230`), and derives the credential it authenticates with from the migration DSN (`:122-129`). A capability login cannot alter another role's password. Migrations additionally create and drop **cluster-global** roles (`infra/migrations/postgres/migrate_integration_main_test.go`:18-26), which is why the suite cannot run against a per-run database either.

### 3.2 The pinning pattern

A new `packages/pgtenant` exposes `PinOrg(ctx, tx, orgID)` issuing `SET LOCAL ROLE ibex_app` and then `set_config('app.current_org_id', $1, true)`, in that order, inside the caller's transaction. It extracts what three stores already do correctly — `packages/billing/store.go`:39-45, `packages/ratelimit/config_store.go`:60-63,68 and `services/auth/internal/repository/tenant.go`:21-37 — and applies it to the six stores that set the GUC and never pin:

| Store | Line |
|---|---|
| `packages/directive/store.go` | `setOrgRLS` at `:78-85` — GUC only |
| `packages/modelpolicy/store.go` | `setOrgRLS` at `:112-118` — GUC only |
| `packages/session/rls.go` | `setOrgRLS` at `:11-19` — GUC only |
| `packages/budgetledger/ledger.go` | `setOrgScope` at `:546-551` — GUC only |
| `packages/idempotency/ledger.go` | `:113` and `:229` — GUC only |
| `packages/evidenceoutbox/store.go` | `setOrgRLS` at `:241-248` — GUC only |

The shared Python ledger has the same gap in its defaults: `service_account_session` sets only `app.is_service_account` (`packages/ibex_idempotency/src/ibex_idempotency/sessions.py`:25-43) and `service_org_session` sets the bypass flag plus the org GUC, never a role (`:44-64`, statements at `:54` and `:59`).

### 3.3 Why this is load-bearing

Under the owner login a missing pin is **invisible**. The owner is the `POSTGRES_USER` the image creates (`infra/compose/v1-single-node/compose.yml`:56) and is the only superuser in the cluster (`infra/migrations/postgres/tenancy_roles_integration_test.go`:30), so RLS is not applied to it; and `set_config(…, true)` is transaction-local, so outside a transaction it is a no-op that looks like success. Under `ibex_runtime` the same bug is `42501`, a hard error. The repository states this where it already got it right: "The capability logins are NOINHERIT and hold no table grant of their own, so the org GUC alone is not enough … Without the role pin a capability DSN fails the read with SQLSTATE 42501" (`packages/ratelimit/config_store.go`:60-63). `ibex_runtime` holds `USAGE` on the schema and **no table grant** — the 68 table grants go to `ibex_app` (`000064`:152 and the `TO ibex_app` grants across the migrations).

### 3.4 The three binding fixes

| Row | Defect today | Fix |
|---|---|---|
| `S01` | `_authorize` compares one static bearer token and nothing else (`services/worker/app/enqueue_http.py`:68-77); `org_id` is then read from the same body (`:137-149`). | Implemented. The proxy mints a 60 s HMAC claim `v1:<org>:<agent>:<session>:<jti>:<exp>` and sends it as `x-ibex-claim` (`services/proxy/internal/extractionenqueue/client.go`:38-44,92-108); the worker verifies the MAC, the expiry (5 s skew), and claim-to-body equality for org, agent and session, refusing a mismatch with 403 (`services/worker/app/enqueue_http.py`:105-160); the ledger then uses the verified claim's org, not the body (`:304-312`). The client stays fail-open by design, so a rejection is a missing extraction, visible only through the metric. **Residual:** the signing key is the same secret as the bearer (`client.go`:9-13; `enqueue_http.py`:122-126), so a leaked bearer can still forge a claim; the claim's value is that the tenant is no longer an unsigned body field and is bound to agent, session and a short expiry. A separate claim secret is a config change, not a contract change. |
| `S05` | Context sends one static PAT as the bearer on every call (`services/context/app/clients/memory.py`:148) from a single configured secret (`services/context/app/config.py`:95). | Context now sends `X-Ibex-Org-Id` for the org it is serving (`services/context/app/clients/memory.py`:30,8-10); memory compares it to the token's org and refuses a mismatch with 403 `ORG_MISMATCH` before any read (`services/memory/app/deps.py`:112-147). The tenant is still derived from the validated token — the header can only narrow access, and an absent header keeps the token's org so an older context deployment still works during rollout. The leakage half was already closed: context binds the request selectors to the verified principal (`services/context/app/principal.py`:85-91). What remains open is **availability, not leakage**: one PAT bound to one org, so serving a second org needs a per-org credential lookup (`§3.7`). |
| `S04` | One static secret admits `ValidateOperatorSession`, `RevokeOperatorSession`, `ConsumeStepUp` and `IssueOperatorSession` (`services/auth/internal/grpc/authz.go`:25-29,105-110), compared in constant time with no reference to the org it acts on (`:61-76,112-125`). | The secret is now **two**, with different authority: `IBEX_AUTH_LIFECYCLE_TOKEN` admits validate, revoke and step-up; `IBEX_AUTH_ISSUE_TOKEN` admits issue and nothing else (`services/auth/internal/grpc/authz.go`:39-61). The auth service refuses to start when they are equal or missing outside development (`services/auth/internal/config/config.go`:93-104). The API presents `x-ibex-expected-org` as gRPC metadata on validate, revoke and step-up; the auth service compares it to the session's org and refuses a mismatch (`services/auth/internal/grpc/authz.go`:25,145-159,168-180). Validate and revoke still carry no org in their request messages (`packages/proto/proto/ibex/auth/v1/auth.proto`:263-265,275-285), so **metadata, not a new field, is what keeps this change free of a proto regeneration**. The split is not a boundary against a compromised API: that process holds both values and can assert any org (`:52-57`). |

### 3.5 The readiness-probe hazard

`has_table_privilege(current_user, …)` measures the identity the transaction runs as. Under `ibex_runtime` an unpinned probe sees a login with no table grant and reports "not ready" forever, although the ledger itself is fine — the probe is measuring the wrong identity.

Where the hazard actually lives:

- **The rule.** Any caller of `PostgresIdempotencyLedger.ping()` (`packages/ibex_idempotency/src/ibex_idempotency/ledger.py`:128-148) under `ibex_runtime` reports not-ready without a **pinned probe scope**, because `ping()` asks the catalog for `SELECT`/`INSERT`/`UPDATE`/`DELETE` on `ibex_core.idempotency_ledger` as `current_user`, and the capability login holds no table grant.
- **The worker is the only `/ready` that calls it**, and it injects a pinning probe scope: `services/worker/app/enqueue_http.py`:187 calls `ping()`; the ledger is built with `probe_scope=app_probe_scope(factory)` at `:442-446`; the scope is `services/worker/app/db.py`:264-268, with the reason written at `:25-29,198-216`.
- **Memory's `/ready` never calls `ping()`.** It checks auth gRPC, Postgres (`SELECT 1`) and Redis (`services/memory/app/probes.py`:38-79,156-167). The ledger is still constructed with a pinning probe scope (`services/memory/app/main.py`:169-176; `services/memory/app/ledger_scope.py`:85-88), so a future `/ready` that did call `ping()` would be green — memory readiness is not the casualty of the flip.
- **The API does not probe the ledger at all** — it checks auth gRPC, Postgres and Redis (`services/api/app/probes.py`:33-88), and `SELECT 1` needs no table grant.

So the stage-1 task was not "fix the API". It is: **any new caller of the shared ledger must inject a probe scope that pins `ibex_app` first, and a test must prove the pinned probe is green under `ibex_runtime` while the unpinned default is `42501`.** The worker test is the model (`services/worker/tests/integration/test_worker_tenant_pinning_readiness_postgres.py`:175-217).

### 3.6 Rollout order and rollback

1. **Pins first.** Land `packages/pgtenant` and apply it to the six stores and the Python defaults. This is inert under the owner login: `SET LOCAL ROLE ibex_app` succeeds for `ibex` (`GRANT ibex_app TO ibex`, `infra/migrations/postgres/000004_rls.up.sql`:33).
2. **Provision.** Run `make v1-provision` so the four capability logins leave `CONNECTION LIMIT 0`.
3. **Flip the DSNs.** Six lines in the profile: bootstrap `:268`, auth `:306`, proxy `:349`, api `:405`, memory `:452`, worker `:548` (`infra/compose/v1-single-node/compose.yml`). Migrate (`:209`) and provision (`:239`) are untouched, because both must alter other roles.
4. **Assert at startup.** Each service asserts `current_user` is its expected capability role, modelled on `services/relay/internal/bootstrap/wire.go`:155-167, and that the role is not the owner and not a superuser: `services/proxy/internal/bootstrap/postgres.go`:241-306, `services/auth/cmd/auth/login.go`:17-84, `services/api/app/db.py`:25-80, `services/memory/app/capability_login.py`:20-72, `services/worker/app/db.py`:56-148. A wrong-password DSN already fails the connection; the assertion catches the case a password cannot — a DSN that authenticates successfully on the owner login.
5. **Rollback** is reverting those six DSN lines and restarting the stack. The pins stay; they are correct under either login.

**The flip was live-proven on 2026-11-15, and this is what the proof is.** `make v1-up` on the `v1-single-node` profile brought all 13 health-checked containers up healthy. No application container connects as `ibex`: `pg_stat_activity` shows `ibex_bootstrap`, `ibex_auth`, `ibex_runtime` (proxy, api, memory) and `ibex_worker`, with only the one-shot `migrate`/`provision` run on the owner. A cross-tenant read issued on the `ibex_runtime` login without the role pin fails `42501` (`infra/scripts/check-tenant-pin.py` is the static half of that rule). At route level a request naming another org returns `403` rather than the other tenant's rows. That is a live cross-tenant read plus the integration suites named in §3.8 — **not** a full acceptance suite, and not a two-tenant browser journey (`P0-21`, `P2-07`).

### 3.7 Deliberately deferred to stage 2, and why

| Deferred | Why |
|---|---|
| `S04` **per-org authority** | The credential split has landed (§3.4), but both credentials are still per-install, not per-org: a compromised API holds both and can assert any org (`services/auth/internal/grpc/authz.go`:52-57). Per-org credentials or mTLS caller identity need the per-org credential lookup and the rotation lifecycle (`P1-17`), so they belong to stage 2. |
| Context serving more than one org | Needs a per-org credential lookup. The gap is **availability, not leakage**: request selectors are already bound to the verified principal (`services/context/app/principal.py`:85-91). |
| Per-org credentials | The per-org-token option for `S01` multiplies secrets and needs rotation on org deletion (`36` §3). Not required for the claim; the org claim plus the metric is. |
| The relay login | `ibex_evidence_relay` is `NOLOGIN` (`infra/migrations/postgres/000036_evidence_plane.up.sql`:24), revoked from `ibex_app` (`:32`) and absent from the provision targets (`provision.go`:47-71), so the relay cannot connect at all today. Granting it a login is stage 2, with the relay's own evidence work. |

### 3.8 Task list

| ID | Objective | Files | Acceptance test | Risk |
|---|---|---|---|---|
| **T1.1** | Add `packages/pgtenant` and pin the six Go stores | `packages/pgtenant/`, the six stores in §3.2 | Integration test on the `ibex_runtime` DSN: a GUC-only transaction fails `42501`; the same transaction through `PinOrg` reads org A's rows and zero of org B's | A store that runs outside a transaction silently no-ops; the test must assert the error, not the row count |
| **T1.2** | Pin the shared Python ledger defaults and inject a probe scope | `packages/ibex_idempotency/src/ibex_idempotency/sessions.py`:31-109, `services/memory/app/main.py`:169-176 | Same negative as T1.1 for `service_account_session`; a pinned `ping()` is green under `ibex_runtime` | Memory's injected scope already pins (`services/memory/app/ledger_scope.py`:85-88); a careless edit regresses a working path |
| **T1.3** | Provision and flip the **six** DSNs, with a startup identity assertion | `infra/compose/v1-single-node/compose.yml`:268,306,349,405,452,548; `infra/compose/v1-single-node/.env.example`; `infra/scripts/dev-tool.sh` | `make v1-up` reaches ready with every service on its capability login (live-proven 2026-11-15); each service fails startup on the owner or a superuser; a wrong-password DSN fails the start, not the first request | A missing grant surfaces as 503 on a read path that is green today; the assertion must run before readiness |
| **T1.4** | `S01`: proxy-minted org claim, worker verifies | `services/proxy/internal/extractionenqueue/client.go`:38-44,92-108; `services/worker/app/enqueue_http.py`:105-160 | Negative: a valid claim for org A with a body naming org B returns 403 and queues nothing; an enqueue-rejection counter increments | The client is fail-open by design, so the failure is missing extraction, not an error to the caller — the metric is the only detector |
| **T1.5** | `S05`: `X-Ibex-Org-Id` on the memory call and its check | `services/context/app/clients/memory.py`:30,8-10; `services/memory/app/deps.py`:112-147 | Negative: header org A with a token for org B returns 403 before any read | If memory ignores the header the change is cosmetic; the test must assert the refusal, not the header |
| **T1.6** | `S04`: `x-ibex-expected-org` on validate, revoke and step-up | `services/auth/internal/grpc/authz.go`:145-180; `packages/authclient/` client | Negative: a credential scoped to org A is refused when the token belongs to org B, for each of the three methods; `ValidateToken`'s bypass (`:63-65`) is asserted to be unchanged | A metadata key the client does not send is silently absent; the check must fail closed when the header is missing for these three methods |
| **T1.7** | Cross-tenant suite with the service-account bypass unavailable | `services/api/tests/`, `services/proxy/internal/`, `services/memory/tests/`, `services/console/e2e/` | Green at route level, on the proxy/chat path and in a two-tenant browser journey, with `app.is_service_account` unset (`000004_rls.up.sql`:10,22 is the clause being suppressed) | Fixtures that rely on the bypass will fail; that is the point, and they must be converted rather than exempted |
| **T1.8** | `P2-22` login rate limit and `S14` log rule | `services/api/app/` middleware and rate-limit config; `services/memory/app/errors.py`:11-22 and the raise sites it governs | 429 on the login route above the configured rate; a test that no raise site interpolates tenant content into an exception message | A limit low enough to block the stage-4 login journey; the rule is a convention, so it needs a test that fails on a violation |

Dependencies: T1.1 and T1.2 before T1.3. T1.4, T1.5, T1.6 and T1.8 are independent of each other and of T1.1–T1.3. T1.7 last.

**Regeneration.** T1.6 as specified needs **no** proto change and no `buf generate`, because the expected org travels as metadata and `ConsumeStepUp` already has the field. If it is instead added to `ValidateOperatorSessionRequest`/`RevokeOperatorSessionRequest`, that becomes its own step: `buf generate`, the generated Go stubs, and the contract registry (`engineering/architecture-v2/contracts/rest-route-registry.json`, checked by `check_contract_registry.py`) must all move in one commit, or the registry gate fails.

---

## 4. What would make this plan wrong

- **If `ibex_runtime` lacks a grant the proxy or memory needs, the DSN flip must wait for a migration.** The runtime login holds `USAGE` on `ibex_core` and membership in `ibex_app` (`000064`:96,152); every table grant belongs to `ibex_app`. A store that reaches a table through a path other than the pinned transaction — a `SECURITY DEFINER` function, an unpinned read, a migration helper on the service DSN — fails closed on the flip. The flip is only safe after T1.1/T1.2 and after a grant review of the proxy's and memory's query set.
- **If the six stores are not all reached inside a transaction, `SET LOCAL` is a no-op and the pin changes nothing.** Each `setOrgRLS`/`setOrgScope` takes a `*sql.Tx` today, but a future caller that passes a `*sql.DB` would silently lose the pin. T1.1's acceptance test must assert `42501` from the unpinned path, which is the only thing that proves the pin is load-bearing.
- **If `S01`'s HMAC key is shared with anything that can mint for another org, the claim relocates the problem instead of removing it.** `36` §3 states this: claim-to-body equality proves the token was minted for the org the body names, not that the issuer was entitled to act for it. Without a verifier-side org authority the fix is a signature, not an authorization.
- **If the erasure fan-out cannot complete within a deadline the product can state, `S09` becomes a claim change, not a code change.** `36` §6 offers both outcomes: receipted asynchronous fan-out with a named deadline, or a narrowed erasure claim (PostgreSQL plus the idempotency record) for v1. Decision 1 makes the second outcome expensive, so stage 2 must budget for the first.

### 4.1 Corrections applied while verifying this plan

Every citation above was opened at `d64eddbb`, then re-opened on 2026-11-15 after the stage-1 flip. Eight statements in the source documents or the brief did not match the tree; the tree won.

| Claim as written | What the tree shows |
|---|---|
| The probe hazard makes "the API never become ready" | The probe is the **worker's** enqueue `/ready` (`services/worker/app/enqueue_http.py`:88-100), already fixed (`:339-342`, `services/worker/app/db.py`:136-150,200-204). The API does not probe the ledger (`services/api/app/probes.py`:33-88). §3.5 records this. |
| `S10` lives at `memory_write_support.py`:541-560 | That file is 238 lines. The code is `services/memory/app/routers/memory_forget_support.py`:50-70, called from `services/memory/app/routers/memories.py`:198-204. |
| "81 runs unrecorded" | `python3 benchmarks/scripts/check_reproducibility.py` at this commit reports **146** unrecorded runs across 5 artifacts. The proxy artifact was added by the stage-1 `R04` closure (`35`:82), which is why the count grew from the 81 that `35`:299 records at `55a62bc4`. The decision is unaffected; the number is. |
| Rollback is "four DSN lines" | **Six**: bootstrap, auth, proxy, api, memory, worker (§3.6). Auth is on the owner login too (`compose.yml`:306), `ibex_auth` is a provision target (`provision.go`:67-71), and bootstrap moved off the owner once the `ibex_bootstrap` definers landed (`compose.yml`:268). |
| "Bootstrap stays on the owner login for v1" | False since the flip. The profile's bootstrap service connects as `ibex_bootstrap` (`compose.yml`:268), which holds no memberships and reaches tables only through `SECURITY DEFINER` functions (`000069_bootstrap_definers.up.sql`:7-14). §3.1 records the new model. |
| "Memory's `/ready` breaks under `ibex_runtime`" | It does not: memory's `/ready` never calls `ledger.ping()` (`services/memory/app/probes.py`:38-79,156-167), and the ledger is constructed with a pinning probe scope anyway (`services/memory/app/main.py`:169-176). The correct rule is about *any* caller of `ping()` (§3.5). |
| `services/auth/internal/grpc/authz.go`:28-33 and `:62-90` | `serviceLifecycleMethods` is `:25-29`; the interceptor is `:61-76`; `isServiceLifecycleMethod` is `:105-110`; `validServiceToken` is `:112-125`. The substance is unchanged. |

Line drift of this kind is expected in `35`/`36`, which were written against earlier commits; it is recorded here rather than silently reused.
