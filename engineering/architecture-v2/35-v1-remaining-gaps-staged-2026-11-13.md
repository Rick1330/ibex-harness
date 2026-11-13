# Remaining v1 gaps, staged — 2026-11-13

**Title:** Every gap still standing between the tree and an honest `v1.0.0`, classified into four stages with the evidence that closes each stage.
**Base:** `main` at `55a62bc4` (2026-11-13).
**Status:** Discovery record, updated by the 2026-11-13 stage-1 pass. It classifies; the pass closed 21 stage-1 rows and is recorded in §3.1 with one line of evidence each. No other stage is re-staged, no ledger row changes value, and no review date moves. The only repository change in the original record was this file plus one link line in [`34-readiness-audit-addendum-2026-11-13.md`](34-readiness-audit-addendum-2026-11-13.md) §5; the stage-1 pass also lands the code, workflow, and documentation changes its rows name.

## 1. Purpose and method

The audit ([`27-v1-readiness-audit.md`](27-v1-readiness-audit.md), 22 P0 / 51 issued P1 / 25 P2), the gap register ([`18-gap-register.md`](18-gap-register.md), 12 GAP) and the release plan ([`31-v1-release-plan-2026-11-09.md`](31-v1-release-plan-2026-11-09.md), 38 W-wave items) describe the same unfinished product from three angles. The addendum ([`34-readiness-audit-addendum-2026-11-13.md`](34-readiness-audit-addendum-2026-11-13.md)) re-verified them at `708a42d6`. None of the three answers the question a reader actually has: **in what order does this get worked, and what evidence ends each block?**

This document answers that and nothing else. Each gap appears **once**, in exactly one stage or in §7, with the blocker class and the file that records it. An item that is not required for v1 is listed with a reason, so nothing is dropped silently.

**Method — four independent read-only sweeps at `55a62bc4`:**

1. **Documented-open items.** 27 §3–§5, 18, 31 §4, 34 §1–§2 read row by row; each ID placed from its own text.
2. **Security / tenancy.** Data-access, authz and secret paths opened directly: DSNs and role pins, step-up mask, service-token interceptor, auth-only routers, erasure path.
3. **Operability / recovery / CI.** Backup, drill, readiness, rate-limit and alerting paths; every workflow that is described as a gate checked for an invocation.
4. **Product / console / evidence.** Console routes, surfaces, navigation, README, claims checker, published artifacts.

Where a sweep disagreed with a document, the tree won and the correction is recorded in §8. Every `file:line` in the tables was opened at `55a62bc4`; rows that cite a document line cite that line as the record of the gap. The 2026-11-13 stage-1 pass re-opened each stage-1 row against the branch, closed 21 of them with the evidence in §3.1, and left four with their residual named in §3.2.

## 2. Stage overview

| Stage | Retires | Why it is in this order | Hard prerequisite for the next |
|---|---|---|---|
| **1 — Make the light honest** | false-green gates, unreviewable contracts, contradicting records | every later stage's exit evidence is read through these gates and documents; proving them first stops stages 2–4 from banking evidence that is not checked | **Yes.** A stage-2 drill record or stage-3 negative suite is only worth what its gate proves |
| **2 — Survive failure** | host loss, silent dependency failure, unreachable pages | data loss is the one failure a release cannot repair after the tag; it needs no product change and unblocks the release gate | No for stage 3; **yes** for the tag (a release needs a restore) |
| **3 — Scope the tenant claim** | cross-tenant read, ungated sensitive read, partial erasure | confidentiality failure is unrecoverable reputationally; it needs the registry and claims from stage 1 to state what is claimed | No for stage 2; **yes** for the tag (the claim must be enforced, or narrowed) |
| **4 — Ship it** | unusable Console, unsigned release, irreproducible numbers, a profile never started in production | consumes the evidence produced by 1–3; doing it earlier ships a product whose claims are unbacked | terminal |

Stages 2 and 3 are independent of each other and can run concurrently. Stage 1 must precede both. Stage 4 must follow all three. `P0-22` sits in stage 4, not stage 3, because its acceptance is a run against the shipped profile (`31`:57) and the stage-4 smoke path is the only gate that exercises one; stage 3 keeps the tenancy rows.

Each stage states the same closure rule: **the stage exits when every row in the table is closed *and* the evidence in its exit gate exists.** A gate item names the rows it evidences. Rows no gate item names are closed by the closure rule alone — they need a merged change with its recorded evidence, not a new run.

## 3. Stage 1 — Make the light honest (gates and record) — 25 rows (21 closed; 4 remaining)

**Goal.** Every check described as a gate runs on a pull request, can fail, and covers what its description claims. Every registry and record matches the tree.

**Why this stage / order.** Three of the strongest-looking controls were advisory or absent when this document was
written: `buf-breaking` was `continue-on-error: true`, the reproducibility checker had no workflow caller, and two
`repo-guards` steps existed only in a shell script. The 2026-11-13 stage-1 pass closed those three plus eighteen more
rows (§3.1); the heading's row count is the original scope, not the current one. GAP-001 and R02 still make part of the
claim set hard to trust, which is why the stage is not exited.

**Entry condition.** No credential and no infrastructure, but this stage is not decision-free: it needs approval to edit `.github/workflows/**`, and owner answers on P1-46 (the support window), GAP-001 (one owner for the claim set), and D-B (whether the Helm chart is part of 1.0 at all).

**Exit gate.** The stage exits when every row in §3.2 is closed *and* the evidence below exists.

1. Each named gate runs in a workflow on a PR and **fails** on a deliberately broken input: `buf-breaking` (P0-12), `api-breaking.sh` (P0-13), bundle smoke (P1-11), the ranking gate as a required check (P1-25), `check-alert-routing.py` + `slo-rules-check.sh` (G03), a ClickHouse schema-evolution gate (P2-03), and the claims checker over the widened roots (R02). Closed for every item except bundle smoke's **manifest half** (P1-11) and the widened claim roots (R02).
2. The contract registry covers **every** shipped REST route, gRPC method and MCP tool, and a new unregistered surface fails CI (P0-14, alias GAP-003; R01). A committed MCP descriptor is diffed against the previous commit and a schema change without a deprecation record fails (P1-02), with the deprecation policy itself validated by its checker (P1-01). **Closed.**
3. Claim consistency is proven by **two named checks, because one cannot see the other's files**:
   (a) **`check-claims.mjs`, widened and run.** It reads four roots — `site/app/pages`, `site/content/docs`, `site/content/blog` (`site/scripts/check-claims.mjs`:14) and `site/app/data` (`:24`) — and skips `adr`/`roadmap-archive` (`:30`). Widening it to `site/app/components/**` and `site/public/benchmarks/*.json` is **R02 and remains open**; the two Console docs pages P1-44 named are now correct by content, not by a widened check.
   (b) **A separate scripted consistency check, `check-status-vocabulary.py`.** It compares the status and availability text in `engineering/architecture-v2/00-status-and-evidence.md`, `engineering/adr/0089-product-shape-and-console-scope.md` and the declared tier/availability in `services/console/shared/operator/surfaces.ts` against each other and against `site/app/data/ledger.ts`, and fails on a mismatch. The claims checker never reads `engineering/**` or a `.ts` module outside `site/app/data`, so it can never evidence those files. **Not landed**; R03 and P1-03 were corrected by hand instead, and GAP-001 therefore stays open.
4. `check_reproducibility.py` runs in a workflow and fails on a deliberately malformed artifact (G01, G02), and covers the proxy latency artifact or states in one line why it is exempt (R04). The unrecorded-run warning is **not** a stage-1 condition: it becomes an error at stage 4 when provenance exists (D03). **Closed.**
5. The records match the tree: the quickstart's first command works from a clean checkout (P1-43), the public env reference names the operator variables (P1-45), the upgrade guide and support window exist (P1-46), `API_DOCUMENTATION.md` no longer says the chat route returns `501` (P2-04), the management API reference lists the live operator reads (P2-23), the migration suite is hermetic (P2-10), and `DATABASE_SCHEMA.md` is generated from every table with a drift check (P2-11). **Closed except P1-46's support window**, which stays open as an owner decision.

### 3.1 Closed in this change (21 rows)

Each row is closed by a merged change in this tree; none is a claim that a hosted run exists.

| ID | What the tree now shows |
|---|---|
| P0-12 | `buf-breaking` has no `continue-on-error`, runs as a job on a PR, and is a `needs` child of `ci-gate-go` (`.github/workflows/ci.yml`:380-408, :3153-3211), which is a protected context |
| P0-13 | `api-breaking` is a job (`.github/workflows/ci.yml`:416-447) and a child of `ci-gate-go` (:3162) |
| P0-14 | The registry carries `routes` (75), `grpc_methods` (20), and `mcp_tools` (8); `check_contract_registry.py` derives the expected set from the proto tree and the descriptors and fails on a missing or stale row |
| P1-01 | `services/api/app/middleware/deprecations.py` and `services/proxy/internal/http/deprecations.go` emit `Deprecation`/`Sunset` for an announced, header-implemented, unexpired entry; the record stays empty because nothing is deprecated |
| P1-02 | `infra/scripts/mcp-memory-test-ci.sh`:20-39 (`--check-base` against the PR base ref) and the same in `mcp-operator-test-ci.sh`; both CI jobs fetch the base branch first (`.github/workflows/ci.yml`:1385, :1451) |
| P1-03 | ADR-0084 is `Accepted` for its five shapes with runtime provisional; ADR-0092, 0093 and 0094 are `Accepted` on named importers; ADR-0095 is `Accepted, partially wired` |
| P1-25 | `ci-gate-memory-benchmark` is always-run and a protected context (`.github/workflows/memory-benchmark.yml`:917-949; `.github/branch-protection-main.json`) |
| P1-43 | The quickstart uses `make v1-secrets` and the tracked `infra/compose/v1-single-node/.env.example`; the copy-a-root-`.env.example` step is gone (`site/content/docs/12.deployment/05.v1-single-node.md`:22-30, :124) |
| P1-44 | The Console pages say 8 of 10: `site/content/docs/02.architecture/01.overview.md`:91, `05.status-and-evidence.md`:59, `site/content/docs/11.operations/08.console.md`:14 |
| P1-45 | `site/content/docs/12.deployment/02.environment-variables.md`:82-101 lists `IBEX_OPERATOR_*` and the two Console origins |
| P2-03 | `infra/migrations/clickhouse/destructive_ddl_unit_test.go` refuses destructive DDL and has a reviewed-exception record; it runs with the ClickHouse migration tests (`.github/workflows/ci.yml`:579) |
| P2-04 | The `501` block lists only `PROVIDER_NOT_CONFIGURED`, and the "returned `501` before provider forwarding landed" sentence is replaced (`engineering/API_DOCUMENTATION.md`:334-336, :61) |
| P2-10 | `infra/migrations/postgres/migrate_integration_main_test.go` isolates each run in its own database and cleans a killed run's leftovers |
| P2-11 | `infra/scripts/check-schema-doc.py` runs in `ci-gate-repo` (`.github/workflows/ci.yml`:110) and compares both directions |
| P2-23 | `engineering/API_DOCUMENTATION.md` now lists every mounted operator route and the tenant management routes from the inventory |
| G01 | `check_reproducibility.py` runs in CI (`.github/workflows/ci.yml`:117-131) |
| G02 | `IBEX_REQUIRE_JSONSCHEMA=1` turns a missing validator into a failure and `jsonschema` is installed first, in both `benchmark-gate` (`.github/workflows/ci.yml`:1091-1103) and `verify-benchmark-pipeline` (`.github/workflows/benchmark.yml`:105-117) |
| G03 | `check-alert-routing.py` runs in `ci-gate-repo` (`.github/workflows/ci.yml`:103) and `slo-rules-check` is its own job feeding `ci-gate-repo` (:338-356, :3127) |
| R01 | All 20 contract IDs declared in `surfaces.ts` resolve in the registry; `services/console/tests/surfaces.test.ts` fails on one that does not |
| R03 | ADR-0089 §2's table now matches `surfaces.ts`: 8 core `live` with registry contracts, 2 core `preview` design, 8 platform `preview` design, and the module is named as the source of truth |
| R04 | `check_reproducibility.py` validates the proxy latency artifact (`benchmark-data.json`) through `PROXY_ARTIFACT_NAME` instead of exempting it |

### 3.2 Remaining (4 rows)

| ID | Gap | Evidence | Blocker | Source |
|---|---|---|---|---|
| P1-11 | Bundle smoke now runs in CI (`.github/workflows/ci.yml`:627-653) and uploads its result, but **wiring the passing bundle into the release manifest is not done**: the manifest still reports `unverified` | `.github/workflows/ci.yml`:614-653; `31`:102 | workflow/branch-protection | 27:102 |
| P1-46 | The upgrade guide now exists (`site/content/docs/12.deployment/06.upgrade.md`) with migration counts, the two irreversible families, the backup precondition, and the rollback limits. **The support window and support matrix are still unsigned** | `site/content/docs/12.deployment/06.upgrade.md`; this file §9 | owner decision | 27:136 |
| GAP-001 | Shipped/local/provisional/design claims conflict across docs. R03 and P1-03 are corrected by hand in this change, but no checker reads `engineering/**`, so the conflict can drift again | 18:7; §3 exit-gate item 3(b) | owner decision | 18:7 |
| R02 | `check-claims.mjs` scans four roots (`app/pages`, `content/docs`, `content/blog`, `app/data`), never `app/components/**` or `public/benchmarks/*.json` | `site/scripts/check-claims.mjs`:14,24 | code | sweep 4 |

A closed row is closed by its own merged change, not by this classification.

**Decisions needed.** An owner for the claim set so GAP-001 stops drifting, and the `check-status-vocabulary.py` script that would make the drift fail instead of relying on hand edits (GAP-001). A signed support window and support matrix (P1-46). Whether the claims checker is widened to `app/components/**` and `public/benchmarks/*.json` (R02). **D-B** — confirm ADR-0097 §10 is the final word on Kubernetes/Helm for 1.0 (`31`:188). D-B decides P2-24: if the chart stays, the digest guard is wired into CI; the default retires the chart and the row goes with it.

## 4. Stage 2 — Survive failure (recovery and operability) — 25 rows

**Goal.** A host loss is survivable from an off-host copy, every dependency failure has a declared behaviour that matches its runbook, and the operator has a backup/restore path that is one command each.

**Why this stage / order.** It is the only block whose failure cannot be repaired after the release: a lost database and a lost backup are one event. It is also the cheapest to start, because it needs no product change and no tenancy decision; and it unblocks the release tag, which cannot be justified while a restore is unproven. It follows stage 1 because the drill record is exactly the kind of artifact that stage 1's gates must be able to fail.

**Entry condition.** Stage 1 exit gate met for the code that reads the drill and backup artifacts (G01/G02/G03, R04); an owner answer on D-D (off-host repository and RPO/RTO numbers).

**Exit gate.** The stage exits when every row in the table below is closed *and* the evidence below exists.

1. A PITR restore from an **off-host** repository to a chosen timestamp, driven by `make v1-backup` and `make v1-restore` (W4.6), with `rpo_pass: true` and an RTO measured against a **signed** target and against a fixture larger than two rows (P0-09, P0-10, P0-11, O03, GAP-011).
2. Post-restore erasure assertion: seed a sentinel memory and an evidence receipt, run the existing forget path, restore, and assert the sentinel is absent from PostgreSQL, ClickHouse, object storage and the idempotency ledger — R05, exercising S09/S10's forget path.
3. A restored provider credential decrypts with the recovered `IBEX_CREDENTIALS_MASTER_KEY`, and the key has its own backup and recovery step (O07, P0-09).
4. A stale backup **and** a failed drill each fire an alert that reaches a human, and the alert is scraped from a live target (O01, O02, P0-19).
5. The runbook-to-failure-mode cross-check passes: a committed table maps Redis, PostgreSQL, ClickHouse, embedder, context, object store and the proxy readiness contract to the failure mode the code implements and the runbook section that matches it; the check fails on a missing or mismatched row (O04, O05, O08, P1-06, P2-20, O07).
6. `make v1-up` proves liveness with an authenticated request, not a static string (O06).
7. Context-assembly and memory-retrieval SLOs and burn rules exist and one synthetic burn fires for each (W6.3); the proxy half is already landed (`31`:145).
8. Every **scrapeable** dependency is scraped and one trace is asserted end to end (P1-48, P1-49). Post-2026-11-12, `api` and `relay` scrape jobs exist and the Tempo round-trip asserts a proxy trace; the stated residuals — the Console's missing `/metrics` route, context's gRPC-only observation, and a trace id not bound to a named request — are what this item still requires (`31`:146).
9. Retention and lag fields are real: `usage_facts` has a retention class (P2-12) and platform ingestion lag is not hardcoded null (P2-21).
10. A load/soak record exists with a stated error policy (P1-47).
11. The evidence plane's acknowledgement boundary is decided and recorded: either the relay fails closed on missing required evidence and the acknowledgement is bound to the response (D4, D11), or the v1 claim states that evidence is post-response and best-effort and the ledger rows say so.

Rows no gate item names: none — all 25 are evidenced above.

**Decisions needed.** D-D: repository type and the signed RPO/RTO table (P0-11, P0-19's delivery half). Whether Redis is allowed to remain the Celery broker while the recovery record calls it ephemeral — the two cannot both be true (O04). Who owns the six missing runbooks (O07). Whether durable-before-ack is a 1.0 claim at all, which decides D4 and D11 rather than closing them by default.

| ID | Gap | Evidence | Blocker | Source |
|---|---|---|---|---|
| P0-09 | No backup in the profile; `pgbackrest` config is `.example` only; no WAL archive | 34:79; 31:44 | infrastructure | 27:64 |
| P0-10 | The committed drill is a `pg_dump` fallback with `rpo_pass: false` | `infra/scripts/platform/evidence/4p5-restore-drill/restore-drill-report.json`:13,15; 34:80 | infrastructure | 27:65 |
| P0-11 | RPO/RTO classes defined, no signed numbers | 34:81; `15-runtime-operations-and-recovery.md`:11 | owner decision (D-D) | 27:66 |
| P0-19 | Routing built, no human paging destination; routing gate not in CI | 34:125; 31:55 | owner decision + workflow | 27:84 |
| P1-06 | Python `/ready` is startup-only for memory; embedder/reranker/Redis absent from readiness | 27:97 | code | 27:97 |
| P1-47 | No load/soak evidence; the one k6 run had 15.7 % failures | 27:137 | benchmark stack | 27:137 |
| P1-48 | Console has no `/metrics` route to scrape and context is gRPC-only (observed indirectly, not scraped); the `api` and `relay` jobs landed 2026-11-12 | 31:146; no `metrics` match under `services/console/server`; 27:138 | code | 27:138 |
| P1-49 | `infra/scripts/observability-live-verify.sh`:319-345 now performs a real Tempo `/ready` + `/api/search` round-trip and prints a proxy trace id, but the search is service-scoped (started after the run) rather than bound to a chosen request, and it runs only via `make observability-live-verify`, not in a workflow | 27:139; 31:146; `infra/scripts/observability-live-verify.sh`:72-73,99-107,319-345 | code | 27:139 |
| P2-12 | `usage_facts` has no TTL/retention class | 27:159 | product | 27:159 |
| P2-20 | `/ready` ignores Redis though operator SSE depends on it | 27:167 | code | 27:167 |
| P2-21 | Platform ingestion lag is a live field hardcoded to null | 27:168 | product | 27:168 |
| GAP-011 | Backup/restore/migration/incident/operator evidence is incomplete | 18:17 | infrastructure | 18:17 |
| O01 | The backup freshness metric is written to a `.prom` file no scrape config reads | `infra/scripts/platform/pgbackrest-backup.sh`:60; no match under `infra/monitoring/` | infrastructure | sweep 3 |
| O02 | `IBEXRestoreDrillMissing` has no producer, so `absent()` fires permanently | `infra/monitoring/prometheus/rules/ibex-platform-backup.yml`:22 | code | sweep 3 |
| O03 | The drill's RTO is ~1 s against a two-row fixture (`INSERT 0 2`) | `restore-drill-report.json`:10,14; `transcript.txt`:7 | code | sweep 3 |
| O04 | Redis is the Celery broker while recovery treats Redis as ephemeral; Redis loss 503s chat; the runbook claims a fallback limiter that does not exist | `infra/compose/v1-single-node/compose.yml`:264; `services/proxy/internal/http/ratelimit_middleware.go`:81-88; `engineering/runbooks/RUNBOOKS.md`:301 | owner decision | sweep 3 |
| O05 | Proxy `/ready` treats PostgreSQL as advisory | `services/proxy/internal/bootstrap/wire.go`:498-506 | code | sweep 3 |
| O06 | `make v1-up`'s proof is a static edge reply with no authenticated request | `infra/compose/v1-single-node/edge/Caddyfile`:19-22 | code | sweep 3 |
| O07 | No runbook for embedder, context, MinIO/S3, master-key loss, TLS expiry, or restore itself | `engineering/runbooks/RUNBOOKS.md` §1-§8 cover proxy, proxy SLO, auth, Redis, PostgreSQL, ClickHouse, worker, isolation only | product | sweep 3 |
| O08 | `RUNBOOKS.md` claims traces spill to disk; the code drops them | `engineering/runbooks/RUNBOOKS.md`:389; `services/proxy/internal/http/session/snapshot.go`:185-193 | product | sweep 3 |
| W6.3 | Context-assembly and memory-retrieval have no SLOs or burn rules (the unshipped half of W6.3); only the proxy overhead rules exist | 31:145; `infra/monitoring/prometheus/rules/ibex-slo.yml` | code | sweep 3 |
| W4.6 | No `v1-backup` / `v1-restore` Makefile targets exist; `Makefile` carries `v1-secrets/up/bootstrap-pat/down/migrate/provision/logs/ps` only | `Makefile`:166-206; 31:98 | code | sweep 3 |
| R05 | The release DoD line "a restore replays markers and receipts" has no row and no gate | 31:209; forget path `services/memory/app/lifecycle.py`:145-177 | code | sweep 3 |
| D4 | No `required_evidence` relay gate exists; the relay is default-off | `00-status-and-evidence.md`:76 | owner decision | sweep 1 |
| D11 | No synchronous response-bound acknowledgement; the finalizer is post-response | `00-status-and-evidence.md`:75 | owner decision | sweep 1 |

## 5. Stage 3 — Scope the tenant claim (isolation, authorization, erasure) — 38 rows

**Goal.** The tenancy and authorization the product claims are the ones actually enforced, and erasure is complete across every store.

**Why this stage / order.** It is the highest-severity residual: a cross-tenant read is unrecoverable, and it is the claim the addendum's own security sweep found least supported (one static token spanning four RPC classes, an auth-only read surface, and erasure that stops at PostgreSQL). It needs stage 1 first because the claim must be stated before it can be either enforced or narrowed — the alternative outcome of this stage is a *smaller* claim, and that choice is only legible once the claim set is coherent. It needs stage 2 only at the tag, because a restore must not resurrect deleted rows.

**Entry condition.** Stage 1 exit gate met for the registry and claim set (P0-14, R01, R03, GAP-001); an owner answer on the P0-06 posture and on the multi-tenant claim question (§9 item 5).

**Exit gate.** The stage exits when every row in the table below is closed *and* the evidence below exists.

1. The cross-tenant negative suite is green **with the service-account bypass unavailable**: at route level, in a two-tenant browser journey, and on the proxy/chat path (P0-06, P0-21, P2-07, GAP-005).
2. Every sensitive read is permission-gated: no route in the four S03 routers, the legal-holds read, or billing read is authentication-only (P1-12, P1-13, S03), and body/array bounds are enforced (P2-08, P2-09).
3. A forget erases content, child rows, embeddings, caches, object-store copies, analytics rows, failed-task rows and the idempotency record, and a failed cache invalidation is retried or receipted (S09, S10, P1-24, P1-21, GAP-005).
4. Each service connects under its own least-privilege role and RLS is actually in force — the org GUC alone is not enough (P0-06, S08, GAP-002).
5. A sentinel/grep test proves no secret is reachable from a process listing, an exported span or a log, and no service token spans unrelated authorities (S01, S04, S05, S06, S07, S11, P1-16). The `PrincipalContext` is signed, or the context-assembly claim records it unsigned in the same change (D6).
6. Org deletion reaches `succeeded` with zero **tenant-content** rows across every store in the profile — excluding retained receipts (`org_deletion_jobs`, `deletion_store_receipts`, `memory_lifecycle_outbox`), billing history (`ibex_billing.*`) and `failed_tasks` (`30-w3-tenancy-and-erasure-plan.md`:117-119) — and ClickHouse/object-store purge is marked `provisional` rather than claimed (`30`:125-126). P0-07 is closed for PostgreSQL; the cross-store half is GAP-005/GAP-011.
7. Auth gRPC outside `development` refuses to start without its TLS certificate and key: a negative test supplies a production config with no cert and asserts the start fails closed (P1-15).
8. Upgrade and migration are rehearsed: a v0.1.9→head run (P1-22), an up→down→up cycle (P1-23), the irreversible families named (P2-14), and keyset grace implemented or removed from the docs (P2-06).
9. Deployed seed cannot mint an owner-role credential (P2-13), service-token rotation and waiver entries are recorded (P1-17, P1-18), and the management API including login is rate limited (P2-22).

Rows no gate item names — S02, P1-14, P2-15, GAP-006, GAP-007, GAP-009 — are closed by the closure rule alone: a merged change with its recorded evidence, not a new run. S02 is **decision-bound as well**: the step-up policy question under **Decisions needed** must be answered before any code change can land, so it cannot close on code alone.

**Decisions needed.** The P0-06 posture: move every service DSN to its capability login, or narrow the tenancy claim. Whether multi-tenant operation is a v1 claim at all (§9 item 5). The S04 split: separate tokens for session issue/validate/revoke and step-up consumption, and org-bound issuance. Whether org deletion requires step-up (S02). Seed policy for a deployed install (P2-13). Whether `PrincipalContext` is signed before a 1.0 claim cites the context-assembly row, or the row records it unsigned (D6).

| ID | Gap | Evidence | Blocker | Source |
|---|---|---|---|---|
| P0-06 | No service DSN is on its capability login; RLS enforced only on paths that already pin | 34:115; 31:41 | owner decision | 27:61 |
| P0-21 | Route-level operator negatives green; no two-tenant browser journey, no proxy/chat negative | 34:116; 31:56 | product | 27:86 |
| P1-12 | `BILLING_READ` is defined but unenforced; no reference under `services/api/app` | 34:117; `packages/authclient/src/authclient/permissions.py`:20 | product | 27:103 |
| P1-13 | `GET .../legal-holds` is authentication-only while the mutation requires the permission | 34:118 | product | 27:104 |
| P1-14 | `mcp-memory` returns `allowed_hosts=[]` with DNS-rebinding protection on | 34:119 | infrastructure | 27:105 |
| P1-15 | Auth gRPC server TLS exists outside `development` but no negative test asserts it | `services/auth/cmd/auth/main.go`:396,424-437 | code | 27:106 |
| P1-16 | OTLP export is cleartext unconditionally | 27:107 | code | 27:107 |
| P1-17 | No service-token rotation; `DEPLOYMENT.md` claims 24 h overlap the code lacks | 27:108 | code | 27:108 |
| P1-18 | `osv-scanner.toml` ignores a nitro advisory absent from the waiver table | 27:109 | owner decision | 27:109 |
| P1-21 | `failed_tasks` has no RLS/prune and stores args/tracebacks that can embed content | 27:111 | code | 27:111 |
| P1-22 | No v0.1.9→head upgrade path or rehearsal | 27:112 | code | 27:112 |
| P1-23 | Down migrations are unproven (no up→down→up cycle) | 27:113 | code | 27:113 |
| P1-24 | Object-store copies are not proven purged; no bucket lifecycle rule | 27:114 | code | 27:114 |
| P2-06 | `JWT_KEYSET_GRACE_SECONDS` is read by no code; rotation has no runbook | 27:153 | code | 27:153 |
| P2-07 | Console BFF has no two-tenant browser evidence | 27:154 | code | 27:154 |
| P2-08 | Memory create takes `agent_id` from the body; the FK surfaces as a 500 | 27:155 | code | 27:155 |
| P2-09 | No whole-body size cap on API/memory/MCP | 27:156 | code | 27:156 |
| P2-13 | Seed on a deployed install can create an active owner-role credential | 27:160 | owner decision | 27:160 |
| P2-14 | Two irreversible migration families; the release note does not name them | 27:161 | product | 27:161 |
| P2-15 | `idempotency_ledger` / `budget_reservations` have no retention/reaper | 27:162 | code | 27:162 |
| P2-22 | No rate limiting on the management API, including login | 27:169 | code | 27:169 |
| GAP-002 | Authority propagation and budgets incomplete | 18:8 | code | 18:8 |
| GAP-005 | Tenant isolation/deletion/evidence coverage not end-to-end proven | 18:11 | code | 18:11 |
| GAP-006 | Reservation/idempotency/reconciliation not accepted as runtime | 18:12 | code | 18:12 |
| GAP-007 | Typed lifecycle/provenance/checkpoint and revision ledger missing | 18:13 | code | 18:13 |
| GAP-009 | MCP/operator boundaries and audit status mixed | 18:15 | code | 18:15 |
| S01 | Worker `POST /internal/extraction/enqueue` takes `org_id` from the body behind one static token | `services/worker/app/enqueue_http.py`:70-81,141 | code | sweep 2 |
| S02 | Org deletion needs no step-up; `ORG_SETTINGS_WRITE` is outside the step-up mask | `services/api/app/authz.py`:105-110; `packages/authclient/src/authclient/permissions.py`:63-74 | owner decision | sweep 2 |
| S03 | Capture-policy, model-policy and rate-limit reads are authentication-only; usage query does not require `BILLING_READ` | `services/api/app/routers/capture_policies.py`:38; `model_policies.py`:55; `rate_limits.py`:75; `usage_query.py`:30-32 | code | sweep 2 |
| S04 | One shared service token admits session issue/validate/revoke and step-up consumption; issuance is not org-bound | `services/auth/internal/grpc/authz.go`:28-33,62-90 | owner decision | sweep 2 |
| S05 | Context calls memory with one static PAT bound to one org | `services/context/app/clients/memory.py`:117 | code | sweep 2 |
| S06 | The Redis password is passed on the container argv | `infra/compose/v1-single-node/compose.yml`:45,49 | credential | sweep 2 |
| S07 | The API holds `auth_service_token`, `jwt_hmac_secret` and `dashboard_csrf_secret` as plain `str` | `services/api/app/config.py`:44,111,145 | credential | sweep 2 |
| S08 | The Go stores set the org GUC but never `SET LOCAL ROLE`, so RLS stays inert | `packages/idempotency/ledger.go`:113; `packages/evidenceoutbox/store.go`:243; `packages/directive/store.go`:80 | code | sweep 2 |
| S09 | A forget leaves S3 capture archives, ClickHouse events and evidence rows readable | `services/memory/app/lifecycle.py`:145-177 (PostgreSQL child rows only; no S3/ClickHouse path) | code | sweep 2 |
| S10 | Post-commit cache invalidation failure on forget is logged, not retried | `services/memory/app/routers/memories.py`:215-221 | code | sweep 2 |
| S11 | MCP servers default `IBEX_ENV=development`, relaxing transport trust if unset | `services/mcp-memory/app/main.py`:79; `services/mcp-memory/app/config.py`:31-33 | code | sweep 2 |
| D6 | `PrincipalContext` is unsigned; the context-assembly claim row cites this limitation | `00-status-and-evidence.md`:72; 34 §1 P1-34 | owner decision | sweep 1 |

## 6. Stage 4 — Ship it (operator product, release integrity, reproducible evidence) — 32 rows

**Goal.** A person can use it, a tag can be cut through the pipeline, the supported profile serves a real request in production mode, and every published number reproduces from that tag.

**Why this stage / order.** It consumes everything the first three stages prove. Doing it earlier produces a releasable-looking artifact whose Console cannot be logged into, whose images are unsigned, whose benchmarks no reader can reproduce, and whose profile has never served a request outside staging — which is the current state. The Console work, the production-start acceptance and the benchmark-provenance work are independent of each other and can run in parallel inside the stage.

**Entry condition.** Stage 1 exit gate met (a release gate must fail when broken); stage 2 exit gate met (a release needs a restore proof); stage 3 exit gate met or the claim narrowed in writing (the release note must not overclaim). Owner answers on D-A, D-C, and the benchmark-publication question.

**Exit gate.** The stage exits when every row in the table below is closed *and* the evidence below exists.

1. A clean-browser journey — login → live page → refresh → logout, no fixture cookie — plus the declared 1.0 Console scope (P0-04, P0-05, P2-05, D01, D02).
2. A release produced by the pipeline from a signed tag, with a signed, schema-validated manifest and per-image SBOMs that verify (P0-15, P1-07, P1-08, P1-09).
3. The supported profile serves one authenticated chat request on `IBEX_ENV=production` plus its two negative cases, and `make v1-smoke` runs green against `v1-up` (P0-22, W7.5; O06 carries the compose half, P1-50 supplies the missing images).
4. Every published number is traceable to a recorded run with runner profile, commit, corpus hash and seed — and reproduces from the tag (P0-20, P1-26, P1-27, P1-33, P1-52, GAP-004, D03, R04).
5. The dependency matrix agrees across dev, bundle, chart and CI (P1-04), and the same commit rebuilds to the same digest (P1-10).

Rows no gate item names — P1-38, P1-39, P1-40, P1-41, P1-42, P2-01, P2-16, P2-17, P2-18, P2-19, P2-25 — are closed by the closure rule alone: a merged change with its recorded evidence, not a new run.

**Decisions needed.** D-A: `VERSION_RELEASE_TOKEN` and the tag-signing key. D-C: Console 1.0 is login + mutations, or login + declared read-only. Whether a v2 ranking number is published at all (P1-26, P1-27, GAP-004). Whether the benchmark gate turns warnings into failures now that the runs are recordable (R04, D03).

| ID | Gap | Evidence | Blocker | Source |
|---|---|---|---|---|
| P0-04 | No login/logout/refresh page; the e2e suite mints a fixture cookie | 34:67; 31:39 | product | 27:53 |
| P0-05 | Every Console BFF route is a read; cookies cannot mutate | 34:68; 31:40 | product (D-C) | 27:54 |
| P0-15 | Release pipeline blocked: manifest `0.1.9`, `VERSION_RELEASE_TOKEN` unset | 34:104; 31:50 | credential | 27:75 |
| P0-20 | HNSW runs carry no provenance; the ranking baseline lacks `sha`, gold-set hash and seed | 34:126; 31:53 | benchmark stack | 27:85 |
| P0-22 | The only recorded start is `IBEX_ENV=staging`, `IBEX_LLM_MODE=mock`; acceptance needs a production-profile start serving one authenticated chat request plus two negatives | 34:73; 31:57 | infrastructure | 27:55 |
| P1-04 | The dependency matrix disagrees across dev, bundle, chart, CI and docs | 34:13-21 | infrastructure | 27:95 |
| P1-07 | Release tags are lightweight and unsigned; no tag protection | 27:98 | owner decision (D-A) | 27:98 |
| P1-08 | The release manifest is not schema-validated or signed at upload | 27:99 | product | 27:99 |
| P1-09 | No per-image SBOM; signatures are produced and never verified | 27:100 | product | 27:100 |
| P1-10 | Memory/embedder run `apt-get upgrade` at build time | 27:101 | product | 27:101 |
| P1-26 | v2 ranking numbers never reach the site | 27:116 | benchmark stack | 27:116 |
| P1-27 | `full_graph == hybrid_rerank`; the gate exists, the corpus equality is unresolved | 27:117; 34:29-30 | benchmark stack | 27:117 |
| P1-33 | The reranker is unnamed/unpinned; the gated row runs `stub/lexical-overlap@1` | 27:123 | benchmark stack | 27:123 |
| P1-38 | CI extraction "quality" is 1.0 by construction (oracle cassette) | 27:128 | benchmark stack | 27:128 |
| P1-39 | Context 50/100 ms targets unmeasured; no live 100K artifact | 27:129 | benchmark stack | 27:129 |
| P1-40 | No tenant provisioning route | 27:130; 34:71 | product | 27:130 |
| P1-41 | Console hand-duplicates Zod schemas from OpenAPI | 27:131 | product | 27:131 |
| P1-42 | Memory returns `{"detail"}` while proxy/API return `{"error"}` | 27:132 | product | 27:132 |
| P1-50 | Relay has no image and is excluded from the manifest; mcp-operator has no publish job | 27:140 | product | 27:140 |
| P1-52 | The 20 ms proxy figure is a target; no published full-chat p99 | 27:142 | benchmark stack | 27:142 |
| P2-01 | Worker registers no-op task skeletons visible on a 1.0 install | 27:148 | code | 27:148 |
| P2-05 | Two of ten core surfaces remain `preview`; Settings is illustrative | 27:152; 31:169 | owner decision | 27:152 |
| P2-16 | `tokens_used` omits tool-schema and formatter overhead | 27:163 | code | 27:163 |
| P2-17 | Token counts are heuristics with 2–5 % buffers | 27:164 | code | 27:164 |
| P2-18 | Capture policies and legal holds are unpaginated | 27:165 | code | 27:165 |
| P2-19 | SSE drain returns an ad-hoc error envelope with no `request_id` | 27:166 | code | 27:166 |
| P2-25 | Dependabot covers Docker for 2 of 8 build dirs; waivers expire silently | 27:172 | code | 27:172 |
| GAP-004 | The 20/40/45/50/100 ms claims conflict and are unmeasured | 18:10 | benchmark stack | 18:10 |
| D01 | Two core `preview` surfaces appear in core navigation with no preview marker; the only `Preview` badge is on the Platform-tier group | `services/console/app/lib/navigation.ts`:107-112; `services/console/app/components/console/AppSidebar.vue`:70-72,90 | product | sweep 4 |
| D02 | `README.md` never reaches the supported `v1-single-node` profile and points at a Console with no login | `README.md`:79-122 | product | sweep 4 |
| D03 | Benchmark artifacts carry run URLs but no corpus hash or seed (81 runs across four artifacts) | `python3 benchmarks/scripts/check_reproducibility.py` → 81 unrecorded; `site/public/benchmarks/ranking-quality-benchmark-data.json` run keys | benchmark stack | sweep 4 |
| W7.5 | No `v1-smoke` target or CI job exists; `grep -rn v1-smoke` hits only documents | 31:158,200 | workflow/branch-protection | sweep 3 |

## 7. Not required for v1

Every P2, every deferred design or ledger item, and the two ledger gate rows `G10`/`G11` that `GAP-010`/`GAP-012` alias in substance (recorded as aliases on those rows, not as separate rows) appears here with the reason it is out. "Post-v1" means the v1 claim is not made, so the gap retires nothing in v1.

| ID | Gap | Why it is out of v1 scope |
|---|---|---|
| GAP-008 | Provider alias/capability/streaming/usage semantics are fragmented | Needs a capability manifest and conformance matrix no v1 surface consumes; ADR-0097 does not claim provider breadth |
| GAP-010 | DecisionService / model registry / calibration / benchmark do not exist (**alias: ledger gate `G10`**, `site/app/data/ledger.ts`:247-253) | Design intent, gated at G10; excluded by ADR-0097 §10 |
| GAP-012 | Graph/A2A/marketplace/sandbox/broad provider expansion is premature (**alias: ledger gate `G11`**, `site/app/data/ledger.ts`:254-260) | Explicitly deferred until the core gates pass (`18-gap-register.md`:18) |
| P1-05 | Embeddings are not shippable for a *semantic* claim | v1 makes no semantic-quality claim; TEI is pinned but no quality evidence exists, so the capability stays `provisional` |
| P1-28 | No human-judged, double-labelled gold set | A labelling programme, not a release gate; no v1 claim depends on kappa |
| P1-29 | v1 gate tolerance cannot catch a single wrong query | Shares P1-28's gold-set dependency; tightening it changes neither the product nor a v1 claim |
| P1-32 | Proxy model overlays are unknown to the context catalog | Model overlays are outside the single-node 1.0 profile |
| P1-36 | Assembly deadline has no reserved pack/format slice | Latency tuning beyond the declared target; not a correctness or claim gate |
| P1-37 | No shadow evaluation or drift alert | Continuous/hosted evaluation; hosted operation is out of 1.0 scope |
| P2-02 | Four shared packages have zero importers; the worker carries a second object-store client | Dead-code cleanup; retires no v1 risk and changes no claim |
| P2-24 | `check-helm-digest-placeholders.sh` is not wired into CI and fails today | Decision-bound to D-B: ADR-0097 §10 retires the chart, so the guard is not v1 work; if D-B keeps the chart, the guard must be wired (`infra/scripts/platform/check-helm-digest-placeholders.sh`; 27:171) |
| P1-30 (remainder) | Re-embed path and backfill; the `embedding_model` fence shipped but bounds only the vector channel — the full-text channels are not fenced (`34`:35) | The fence and inventory shipped; a corpus backfill is a post-v1 migration, and turning the fence on without it would drop the corpus; no v1 claim rests on filtered full-text search |
| P1-31 (remainder) | Licence fields and extraction-alias pinning; the inventory shipped, but extraction defaults still float (`services/worker/app/config.py`:181-214) | Fifteen licence rows need an owner and the inventory is recorded `provisional`; pinning `gpt-4o-mini`/`Qwen2.5-14B-Instruct` is not a v1 gate, and the inventory already records them as floating |
| D1 | No independent reviewer for accepted contract shapes; every G0 acceptance is Rick1330 acting across roles | A process decision, not a repository artifact: the owner names a reviewer or records the limitation before a 1.0 claim cites those shapes (`00-status-and-evidence.md`:58,72) |
| G9 | Governed side effects: operation intent/receipt, approval, exact tool descriptors, egress, credentials, isolated execution | `PROPOSED` and specified only — no runtime or acceptance evidence, so v1 makes no such claim (`site/app/data/ledger.ts`:241-246) |

## 8. Traceability appendix

The completeness proof: per stage and per exclusion, the exact ID sets, then the arithmetic.

**Stage 1 (25 rows: 21 closed, 4 remaining).**
Remaining: `P1-11` `P1-46` `GAP-001` `R02` (4).
Closed in §3.1: `P0-12` `P0-13` `P0-14` `P1-01` `P1-02` `P1-03` `P1-25` `P1-43` `P1-44` `P1-45` `P2-03` `P2-04` `P2-10` `P2-11` `P2-23` `G01` `G02` `G03` `R01` `R03` `R04` (21); `GAP-003` is an alias recorded on the `P0-14` row, not a second row.

**Stage 2 (25 rows).**
P0: `P0-09` `P0-10` `P0-11` `P0-19` (4).
P1: `P1-06` `P1-47` `P1-48` `P1-49` (4).
P2: `P2-12` `P2-20` `P2-21` (3).
GAP: `GAP-011` (1).
NEW: `O01`–`O08` (8), `W6.3` (1), `W4.6` (1), `R05` (1), `D4` (1), `D11` (1) — 13.

**Stage 3 (38 rows).**
P0: `P0-06` `P0-21` (2).
P1: `P1-12` `P1-13` `P1-14` `P1-15` `P1-16` `P1-17` `P1-18` `P1-21` `P1-22` `P1-23` `P1-24` (11).
P2: `P2-06` `P2-07` `P2-08` `P2-09` `P2-13` `P2-14` `P2-15` `P2-22` (8).
GAP: `GAP-002` `GAP-005` `GAP-006` `GAP-007` `GAP-009` (5).
NEW: `S01`–`S11` (11), `D6` (1) — 12.

**Stage 4 (32 rows).**
P0: `P0-04` `P0-05` `P0-15` `P0-20` `P0-22` (5).
P1: `P1-04` `P1-07` `P1-08` `P1-09` `P1-10` `P1-26` `P1-27` `P1-33` `P1-38` `P1-39` `P1-40` `P1-41` `P1-42` `P1-50` `P1-52` (15).
P2: `P2-01` `P2-05` `P2-16` `P2-17` `P2-18` `P2-19` `P2-25` (7).
GAP: `GAP-004` (1).
NEW: `D01` `D02` `D03` (3), `W7.5` (1) — 4.

**Not in v1 (15 rows).**
GAP: `GAP-008` `GAP-010` `GAP-012` (3).
P1: `P1-05` `P1-28` `P1-29` `P1-32` `P1-36` `P1-37` (6 whole) + `P1-30` `P1-31` (remainders) — 8.
P2: `P2-02` `P2-24` (2).
Ledger: `D1` `G9` (2).

**Closed since the audit (not re-listed).** `P1-20`, `P1-34`, `P1-35`, `P1-51`; and the eight P0s `P0-01`, `P0-02`, `P0-03`, `P0-07`, `P0-08`, `P0-16`, `P0-17`, `P0-18`. Each is closed in `34-readiness-audit-addendum-2026-11-13.md` §1 or `31-v1-release-plan-2026-11-09.md` §2 — except `P1-20`, whose closure is recorded in `30-w3-tenancy-and-erasure-plan.md` §3 (`:26,48`), as §8 correction 4 states. Nothing here reopens them. `P1-15` is **not** in this set: no engineering document other than the audit records it, and no negative test asserts its substance, so it stays a stage-3 row (§8 correction 11).

**Closed in the 2026-11-13 stage-1 pass (21 rows).** `P0-12` `P0-13` `P0-14`; `P1-01` `P1-02` `P1-03` `P1-25` `P1-43` `P1-44` `P1-45`; `P2-03` `P2-04` `P2-10` `P2-11` `P2-23`; `G01` `G02` `G03` `R01` `R03` `R04`. Each has its own row and evidence in §3.1; none is re-listed in a stage table. `P1-11` and `P1-46` are **partially** closed and stay in §3.2 with their residual named.

**Arithmetic.**

- **P0: 22 = 11 in stages + 11 closed.** 11 = S1 0 + S2 4 + S3 2 + S4 5; closed = 8 since the audit + `P0-12` `P0-13` `P0-14`.
- **P1: 51 issued = 32 in stages + 8 not in v1 + 11 closed.** 32 = S1 2 + S2 4 + S3 11 + S4 15; closed = 4 since the audit + `P1-01` `P1-02` `P1-03` `P1-25` `P1-43` `P1-44` `P1-45`. `P1-19` was never issued: the audit runs `P1-01`…`P1-18` then `P1-20`, so the numbering skips and the set of issued rows is 51, all placed.
- **P2: 25 = 18 in stages + 2 not in v1 + 5 closed.** 18 = S1 0 + S2 3 + S3 8 + S4 7; closed = `P2-03` `P2-04` `P2-10` `P2-11` `P2-23`.
- **GAP: 12 IDs = 11 rows + 1 alias.** 8 stage rows (S1 1 + S2 1 + S3 5 + S4 1) + 3 in §7 = 11; `GAP-003` aliases `P0-14` and adds no row.
- **NEW and ledger rows: 38 = 30 in stages + 2 in §7 + 6 closed.** 30 = S1 1 + S2 13 + S3 12 + S4 4; §7 holds `D1` and `G9`; closed = `G01` `G02` `G03` `R01` `R03` `R04`.
- **Staged rows still open: 99 = S1 4 + S2 25 + S3 38 + S4 32.** 120 original staged rows minus the 21 closed in this pass.
- **W-waves: 38 items, each mapped once.** 38 = W0 3 + W4 6 + W5 5 + W6 4 + W7 5 + W8 6 + W9 4 + W10 5.

**W-wave → stage map.** Every item in `31-v1-release-plan-2026-11-09.md` §4, accounted for once:

| Wave item | Disposition |
|---|---|
| W0.1 | Closed — P0-16 (`31`:82) |
| W0.2 | Closed — P0-03 (`31`:83) |
| W0.3 | Carried PR #1164; no register ID, not a gap (`31`:84) |
| W4.1–W4.5 | Stage 2 — P0-09, P0-10, P0-11, O01–O08 (`31`:93-97) |
| W4.6 | Stage 2 — W4.6 (`31`:98) |
| W5.1 | Closed — P0-12 (`31`:129) |
| W5.2 | Closed — P0-13 (`31`:130) |
| W5.3 | Closed — P0-14, R01 (`31`:131) |
| W5.4 | Closed — P1-01 (`31`:132) |
| W5.5 | Closed — P1-02 (`31`:133) |
| W6.1 | Closed — P0-18 (`31`:143) |
| W6.2 | Stage 2 — P0-19, O01, O02 (`31`:144) |
| W6.3 | Stage 2 — W6.3; the proxy half landed, the context and memory halves did not (`31`:145) |
| W6.4 | Stage 2 — P1-48, P1-49 (`31`:146) |
| W7.1–W7.4 | Stage 4 — P0-15, P1-07, P1-08, P1-09, P1-10 (`31`:154-157) |
| W7.5 | Stage 4 — W7.5 (`31`:158, :200) |
| W8.0–W8.5 | Stage 3 — P0-06, P0-21, P2-07, S05, S08 (`31`:115-120) |
| W9.1–W9.4 | Stage 4 — P0-04, P0-05, P1-40, P2-05, D01 (`31`:166-169) |
| W10.1 | Stage 4 — P0-20, D03 (`31`:175) |
| W10.2 | Stage 4 — P1-26, P1-27 (`31`:176) |
| W10.3 | Not in v1 — P1-30/P1-31 remainder; inventory half closed (`31`:177) |
| W10.4 | Closed — P1-34, P1-35 (`31`:178) |
| W10.5 | P1-44, P2-04, R03 closed; R02 still stage 1; P1-51 closed and P1-52 in stage 4 (`31`:179) |

**Record corrections (where the sweeps disagreed, the tree won).** Each was verified at `55a62bc4`; the drifted form is not carried forward.

1. `RUNBOOKS.md` is **`engineering/runbooks/RUNBOOKS.md`**. O04 and O08 cite that path; the addendum does not mention it at all.
2. ADR-0089 is **`engineering/adr/0089-product-shape-and-console-scope.md`**; R03 cites it.
3. The Console sidebar is **`services/console/app/components/console/AppSidebar.vue`**; D01 cites the real path. Its only `Preview` badge is on the Platform-tier group header (`:90`), not on the two core preview surfaces.
4. **`P1-20` is closed, not open.** `services/worker/app/tasks/org_deletion_stores.py`:14-31 purges all six ClickHouse tables including `usage_facts` and `evidence_events`; the closure is recorded in `engineering/architecture-v2/30-w3-tenancy-and-erasure-plan.md`:26,48. It is therefore in the closed set, not stage 3.
5. **`P1-51` is closed, not stage 4.** The addendum records the reworded README at `README.md`:14-16 and the absence of the old sentence. The brief's stage-4 membership predates that record; the tree has the reworded text.
6. **`P1-19` was never issued.** No file contains the string. The arithmetic above states 51 issued rows rather than fabricating a row.
7. **R02's four roots are declared in two places**, not one range: `proseRoots` at `site/scripts/check-claims.mjs`:14 and `numericRoot` at `:24`. The claim (four roots, never `app/components/**` or `public/benchmarks/*.json`) holds; the citation is corrected.
8. **O03's "two-row fixture"** is in `transcript.txt`:7 (`INSERT 0 2`), not in the report JSON; the report carries the RTO number at `:10` and the pass flag at `:14`.
9. **R04 verified exactly:** `benchmark-data.json` holds 65 runs and does not match the `*-benchmark-data.json` suffix the checker globs (`check_reproducibility.py`:99), so it was outside the four validated artifacts at `55a62bc4`. Superseded in this pass: the checker now names the proxy artifact through `PROXY_ARTIFACT_NAME` and validates it (§3.1 R04).
10. **R01 verified exactly:** 20 distinct contract IDs were declared across `surfaces.ts`:42-246; 18 were absent from `engineering/architecture-v2/contracts/rest-route-registry.json` at `55a62bc4` (only `operator.evidence.summary.v1` and `operator.platform.health.v1` appeared). Superseded in this pass: the registry now carries all 20 (§3.1 R01).
11. **`P1-15` has no closure receipt, and none is claimed.** It appears in no engineering document other than the audit. Its substance is closed in the tree — `services/auth/cmd/auth/main.go`:396,424-437 builds server TLS credentials outside `development` and fails closed otherwise — but no negative test asserts it, so it remains a stage-3 row rather than a closed item.
12. **`P1-02` is restated exactly as the plan records it (`31`:133).** The descriptors are committed records (`services/mcp-memory/mcp_tools.json`, `services/mcp-operator/mcp_tools.json`) checked in CI at `infra/scripts/mcp-memory-test-ci.sh`:19 and `infra/scripts/mcp-operator-test-ci.sh`:25. The residual is record-to-live-surface only: no previous-commit diff and no deprecation record per schema change.
13. **`GAP-003` is not a second gap.** It is the same defect as `P0-14` (no complete route/proto/event/MCP contract registry), so it is recorded as an alias on that row and adds no row to any count.
14. **`P2-24` is decision-bound, not stage-1 work.** The guard is `infra/scripts/platform/check-helm-digest-placeholders.sh`; whether it is wired or retired depends on D-B (`31`:188), so it sits in §7 rather than in the stage-1 table.

## 9. Open questions

These change the staging itself, not just a row's blocker. Each needs an owner answer before the stage it names can be sequenced.

1. **D-A — release credential and signing key.** Without `VERSION_RELEASE_TOKEN` and a tag-signing key, stage 4 cannot start its release half (P0-15, P1-07, P1-08, P1-09). The default if silent is "no 1.0 tag", which makes stage 4 unclosable.
2. **D-C — Console 1.0 is login + mutations, or login + declared read-only.** This decides whether P0-05, P1-40 and much of stage 4 are in scope or replaced by a one-page scope statement. It changes stage 4's size by roughly a week and changes what "done" means.
3. **D-D — off-host repository and the signed RPO/RTO numbers.** Stage 2's exit gate is defined in terms of a *signed* target; without D-D the drill can be measured but not passed. Silent default: S3/MinIO if available, RPO ≤ 5 min, RTO ≤ 60 min, both drill-measured.
4. **P0-06 posture — move the DSNs, or narrow the claim.** Either every service connects on its capability login and RLS is in force, or v1 does not claim multi-tenant isolation at the database. This is the largest single fork in stage 3: the first is engineering work across six services plus fixtures, the second is a claims change that shrinks the product.
5. **Is multi-tenant a v1 claim at all?** If the answer is no — one tenant per install, stated — then P0-06, P0-21, P1-12/13, S01, S04 and S05 lose their v1 urgency and stage 3 becomes a small claim edit. If yes, stage 3 is the longest block in this document. The question is not answered anywhere in the record; it is currently implied by the ledger's isolation wording, not decided.
6. **R04/D03 sequencing.** Whether the reproducibility checker's unrecorded-run warning becomes a failure before or after stage 4 records the runs. Turning it on today fails on all 81; leaving it a warning keeps stage 4's provenance gate as the only place it becomes an error.
