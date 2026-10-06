# GAP-04 — Governed Memory Lifecycle and Operations: Verified Audit

**Repository:** `Rick1330/ibex-harness`<br>
**Audited ref:** clean `main` at `7298e5ee7982b926630566c88830c99650c8eb37` (`7298e5e`, PR #937 merge)<br>
**Audit mode:** read-only; no repository files or configuration changed<br>
**Scope:** exactly GAP-04 / governed memory lifecycle; adjacent identity, evidence, context, and recovery findings are included only where they are dependencies or shared boundaries.

## Executive finding

**GAP-04 remains open.** The repository has a useful shipped-local memory substrate and PR #936 added an important current-time validity fence to the identified vector, FTS, final-hydration, and hot-cache read paths. That hardening fixes the earlier `valid_until` retrieval defect for ordinary paths at code level. It does **not** create the specified governed lifecycle.

The current implementation still lacks an authoritative typed observation ledger, complete provenance/trust/retention/hold metadata, explicit review/promotion lifecycle, durable per-memory operation state, an individual tombstone/delete API, immediate tombstone semantics, per-memory cross-store fan-out/certificate, and replay/version fencing. The existing org-wide deletion saga and `PgVectorStore.delete()` are materially narrower than the target contract. No current evidence-ledger entry promotes the lifecycle to `shipped-accepted`.

The correct maturity statement is: **memory CRUD/search, tenant filtering, dedup/conflict/supersession, PII quarantine, temporal read fencing, and org-wide deletion are shipped-local or partial local slices; typed lifecycle, per-memory deletion, deletion certification, and profile recovery acceptance remain open.**

## Authority and source reconciliation

Reviewed the assigned memo, strategy, implementation plan, and session report, then verified the clean checkout and current code/tests/docs:

- Assigned memo: `preflight/ibex-preflight docs/gap-04-memory-lifecycle.md`. Its own conclusion (lines 8–14, 65–113) says the substrate is shipped-local, typed projection is not certified, individual deletion/operation status/provenance/review/expiry enforcement/certificates are the major holes, and recommends keeping the gap open.
- Strategy: `preflight/ibex-preflight docs/IBEX Harness_ Product Strategy, Gap Audit, and Recommended Redesign.md`. The product intent is governed memory with mandatory tenant/agent scope, append-only observations, active projections, provenance, valid intervals, supersession, quarantine, redaction, feedback, job status, and deletion propagation (memory section, including the Mem0 comparison).
- Plan: `preflight/ibex-preflight docs/ibex-harness-implementation-plan.md`, especially Phase 4 (lines 88–92), gates (159–168), and definition of done (179–181). It explicitly sequences per-memory tombstone/operation/fan-out before typed context and requires profile-specific deletion/recovery evidence.
- Session report: `preflight/ibex-preflight docs/SESSION_REPORT_2026-10-06.md`, lines 435–449. It explicitly records that no complete per-memory tombstone/operation/receipt/fan-out/replay-suppression implementation was completed.
- Canonical contracts: `web/engineering/architecture-v2/08-context-and-memory-contract.md`, `09-memory-lifecycle-and-deletion.md`, `10-evidence-contract.md`, `00-status-and-evidence.md`, `18-gap-register.md`.

The canonical contract is specified, not accepted implementation: `09-memory-lifecycle-and-deletion.md:3` says `specified` and “typed projection implementation is not yet certified.” The status ledger says memory substrate is `shipped-local` and specifically says not to infer typed projections, deletion certification, or production isolation (`00-status-and-evidence.md:17–24`). The ledger also says a PR merge is not an acceptance artifact (`00-status-and-evidence.md:31–35`).

## Verified current implementation

### 1. Schema and lifecycle vocabulary — local foundation, not a lifecycle ledger

- `infra/migrations/postgres/000014_create_memories_temporal.up.sql:6–70` defines one mutable `ibex_core.memories` row with `status` values `active`, `superseded`, `merged_into`, `archived`, `quarantined`, and `deleted`; `deleted_at`; half-open `valid_from`/`valid_until`; `observed_at`; content hash; and tenant/agent/session foreign keys.
- `000014:104–110` enables/forces RLS and grants ordinary CRUD, which is useful tenant protection but not a deletion authority or evidence contract.
- `000017_memory_schema_v2_expand.up.sql:12–25` adds confidence, source, supersession/merge IDs, embedding metadata, PII flags, and JSON metadata. `:56–58` constrains `source` to `extracted`, `user_provided`, `imported`, or `inferred`; `:73–82` adds same-org relation FKs; `:94–107` adds active/non-deleted retrieval indexes.
- There is **no append-only observation table plus rebuildable active projection** in the inspected memory migrations. `observed_at` is a column/default, not a complete source-event history.
- `services/memory/app/schemas/memories.py:22–57` `CreateMemoryRequest` accepts generic content/category/confidence/session/visibility/tags/metadata/pinned/validity, but not source event/span, actor/purpose, retention class, legal hold, operation ID, model/preprocessing identity, or review authority. `MemoryData:60–80` is similarly not a full provenance envelope.
- `services/memory/app/write/persist.py:89–141` `insert_memory_session` writes a mutable row and hard-codes `source: "user_provided"` at `:109`; it does not set the nullable schema field `created_by_user`. Extraction also writes through the same memory endpoint per ADR-0064/0065 context, so exact end-to-end source attribution is uncertain; the hard-coded current insert behavior is verified.

**Assessment:** existing schema/status vocabulary is **partial** support for lifecycle concepts. It is not verified as the canonical typed observation/projection model.

### 2. Current API and operations

`services/memory/app/routers/memories.py` exposes:

- `POST /v1/memories` → `create_memory` (`:77–115`), synchronous `201` create with Redis-backed idempotency through `begin_idempotency`/`finalize_created_response`.
- `POST /v1/memories/search` → semantic search (`:118–149`).
- `GET /v1/memories/hot` → hot-cache listing (`:152–184`).
- `POST /v1/memories/{memory_id}/feedback` → feedback (`:187–235`).

There is no per-memory `DELETE`, archive/correct/merge/promote/review route, retention/hold route, operation-status route, cancellation route, or deletion-certificate route. `CreateMemoryRequest`/response has no durable operation ID/state contract.

The current idempotency path therefore supports create retry/replay, but it is not the specified durable operation ledger. No `memory_operations`/generic durable operation table or memory-operation state machine was found in current `services/memory` or `infra/migrations/postgres`; no `operation_id`, `queued`, `running`, `cancelled`, or operation-status implementation exists for memory mutations. `infra/migrations/postgres/000025_org_deletion_jobs.up.sql:1–35` is specifically an **org GDPR deletion job**, not a per-memory operation ledger.

### 3. Read eligibility and temporal validity

Current ordinary read SQL has the intended temporal fence:

- Vector: `services/memory/app/vectorstore/pgvector_store.py:15–33` `SEARCH_SQL` filters `status='active'`, `deleted_at IS NULL`, and uses `(:include_expired OR valid_from <= CURRENT_TIMESTAMP)` plus `(:include_expired OR valid_until IS NULL OR valid_until > CURRENT_TIMESTAMP)`.
- FTS: `services/memory/app/read/full_text.py:14–31` `FTS_SQL` filters active/non-deleted and both current validity bounds.
- Final hydration: `services/memory/app/read/repository.py:31–50` `_HYDRATE_SQL` repeats active/non-deleted and current validity bounds.
- Hot-cache hydration: `services/memory/app/read/hot_cache.py:23–35` `_HYDRATE_HOT_SQL` repeats the same guards. Redis sorted-set IDs are rehydrated against Postgres (`hot_cache.py:96–118`), so stale membership alone is not returned as a current row.
- `services/memory/app/vectorstore/base.py:44–60` documents `include_expired` as historical mode reserved for write-time conflict detection, defaulting to `False`.
- `services/memory/app/dedup/service.py:71–93` deliberately sets `include_expired=True` for near-duplicate/conflict candidate detection, preventing historical conflict candidates from being hidden from the write path while preserving the user-read default.

PR #936 (merged commit `125fde3da214649f319cb54e5f87b96f2ed3575c`, parent PR #934 merge) added these read predicates, the explicit historical mode, and `services/memory/tests/unit/test_lifecycle_predicates_unit.py`. The tests assert SQL shape for all four paths (`:19–42`) and `services/memory/tests/unit/test_dedup_service.py` adds `test_near_dup_includes_expired_for_conflict_evaluation`.

**Assessment:** the prior memo finding “`valid_until` is stored but not enforced on retrieval” is **superseded for the four identified authoritative read paths** by PR #936. The code-level ordinary-read predicate is **resolved**. Acceptance evidence remains **partial**, because the current test is string-shape/unit coverage; no DB-backed boundary-time test was identified for each path, and no profile/hosted evidence proves runtime deployment behavior. `include_expired=True` is an intentional internal write-time exception, not a public retrieval bypass, but its callers must remain restricted.

### 4. Quarantine, deduplication, conflict, and supersession

- PII handling exists in the write pipeline. Unit coverage includes `services/memory/tests/unit/test_pii_service.py::test_low_confidence_quarantines_without_redaction`, `::test_mixed_scores_quarantine_wins`; integration coverage includes `services/memory/tests/integration/security/test_memory_iso_3_pii_quarantine.py::test_memory_iso_3_2_quarantined_never_in_search`.
- Exact/near dedup exists. `DedupService.check_exact`/`find_near_duplicates` are in `services/memory/app/dedup/service.py:20–93`; integration coverage includes `services/memory/tests/integration/test_dedup.py::test_exact_cross_tenant_no_match` and near-duplicate tests.
- Temporal conflict/supersession is a real mutation: `services/memory/app/conflict/persist.py:84–136::apply_supersession_session` updates an active row to `superseded`, sets `superseded_by`, closes `valid_until`, and inserts a `supersedes` relationship in the caller transaction. Integration coverage is `services/memory/tests/integration/test_conflict.py::test_apply_supersession_updates_status_and_edge`.
- No human/operator review or promotion API was found for quarantined rows. Existing `pending` conflict escalation storage is not a review/authority lifecycle. No general archive, merge, correction, explicit expire, or deletion transition is exposed by the memory API.

**Assessment:** quarantine/dedup/conflict/supersession are **partial/resolved local slices**, not a governed state machine. The target requires explicit review/authority for promotion, append-only observations, and a rebuildable projection; these remain **open**.

### 5. Individual deletion and tombstones

- The schema has `deleted_at` and a `deleted` status (`000014:31–40`), and all four normal read/hydration SQL paths exclude `deleted_at IS NULL`.
- No memory-service mutation in `services/memory/app` was found that sets `deleted_at` or `status='deleted'`; the public router has no delete route.
- `services/memory/app/vectorstore/pgvector_store.py:124–141::PgVectorStore.delete` only nulls `embedding`, `embedding_model`, and `embedding_dim`. The interface itself says `base.py:115–117` “Clear embedding fields for a memory (does not delete the row).” It is not a canonical tombstone operation and does not purge Redis, FTS/canonical content, object artifacts, analytics, exports, or queues.
- `services/memory/tests/integration/security/test_memory_iso_2_cascade.py::test_memory_iso_2_1_memory_delete_cascades_fk_children` tests database FK cleanup after a database deletion; it is not evidence of an authenticated public delete, immediate tombstone, multi-store erasure, or replay fencing.
- `services/memory/tests/integration/test_hot_cache_stale_integration.py::test_hot_cache_hydrate_filters_soft_deleted_memory` manually updates `deleted_at` and verifies read hydration suppression. `services/memory/tests/integration/test_find_similar.py::test_find_similar_excludes_quarantined_and_deleted` similarly proves filtering of rows already marked deleted, not a mutation protocol.

**Assessment:** the individual tombstone/delete acceptance criterion is **open**. A nullable column plus read predicates does not establish the required authoritative tombstone command, read-after-delete contract, durable operation, or deletion certificate.

### 6. Org-wide deletion is real but has a different boundary

- `infra/migrations/postgres/000025_org_deletion_jobs.up.sql:1–35` defines durable `pending/running/succeeded/failed` **organization** deletion jobs with org RLS.
- `infra/migrations/postgres/000037_privacy_governance.up.sql:281–315` defines org-scoped legal holds only (`scope CHECK (scope='org')`); `:352–396` defines `deletion_store_receipts` with stores `postgres/clickhouse/redis/objectstore`, status, `scope` default `'org'`, and job-level uniqueness.
- `services/worker/app/tasks/org_deletion.py:82–124` deletes org evidence/policy rows and then physically deletes all `memories`/related rows in `_CASCADE_STATEMENTS` (`:104–110`).
- Hold behavior is explicit: `_finish_if_hold_blocked` (`org_deletion.py:309–327`) marks the org job `hold_blocked`; `_require_no_hold` (`:330–337`) serializes store stages against hold creation.
- Optional-store stages cover ClickHouse/Redis/object store (`org_deletion.py:354–405`, `services/worker/app/tasks/org_deletion_stores.py:12–44,134–191`). Redis deletion is prefix-based and object deletion includes org prefix; this is not a per-memory version-fenced fan-out.
- `_finalize_job` (`org_deletion.py:407–430`) requires deployed-store receipts, hashes receipt rows, appends `org_deletion.certificate`, and marks the org job succeeded. `services/worker/app/tasks/org_deletion_receipts.py:68–95` uses an idempotency key of `{job_id}:{store}:org`; `:118–134` hashes receipt status metadata.

**Assessment:** org deletion is a **partial local capability** with org-level hold checks and per-store receipts. It does not satisfy per-memory tombstones, immediate suppression, per-memory completion certificates, or replay fences. The receipt schema’s explicit `scope='org'` and idempotency key prove the boundary. It may be reusable only after a contract decision demonstrates identical per-memory semantics; current code does not.

### 7. Isolation and authorization evidence

Positive local controls include org/agent predicates in all read SQL, Postgres RLS (`000014:104–110`), and tests:

- `services/memory/tests/integration/security/test_memory_iso_1_isolation.py::test_memory_iso_1_1_cross_org_search_empty`
- `::test_memory_iso_1_2_cross_org_agent_forbidden`
- `::test_memory_iso_1_5_hnsw_no_cross_org_leakage`
- `::test_memory_iso_1_hot_cache_agent_isolation`
- PII quarantine exclusion noted above.

These tests do not prove mutation authorization for a delete operation because no such operation exists. A future lifecycle mutation must bind actor/purpose/resource scope, tenant idempotency, anti-enumeration behavior, and no cross-tenant side effects. `legal_holds` are org-scoped and currently only constrain the org purge saga; they do not grant retrieval eligibility.

**Assessment:** read isolation is **partial/shipped-local**; lifecycle mutation authorization and end-to-end deletion/isolation proof remain **open** and overlap P0 GAP-005.

## Acceptance-criterion disposition

The table below treats the GAP-04 memo’s “smallest high-quality slices” (`gap-04-memory-lifecycle.md:74–82`), canonical contracts, and implementation-plan Gate 4 as the acceptance criteria. “Resolved” means verified in current code at this boundary; “partial” means a local slice exists but the criterion’s end-to-end/evidence requirement is not met; “open” means the required capability is absent.

| Acceptance criterion | Classification | Verified evidence and exact gap |
|---|---|---|
| **G0 contract/authority freeze:** ratify memory classes/states, source/actor taxonomy, time semantics, retention/holds, per-memory vs org deletion ownership, operation/idempotency, retrieval eligibility, evidence envelope, profile stores, migration/rollback; named owner/profile/evidence/approval recorded. | **Open** | Canonical lifecycle is still `specified` (`09-memory-lifecycle-and-deletion.md:3`); status ledger says G0 packet is proposed and not accepted (`00-status-and-evidence.md:29–35`); no named acceptance artifact was found. Existing ADR-0055/0056/0057/0060/0065 are narrower write/isolation decisions, not a full lifecycle freeze. |
| **G1/G2 minimal mutation:** tenant/resource-authorized per-memory tombstone, durable Postgres operation record with ID/state, tenant-bound idempotency, atomic tombstone+outbox, operation ID response, idempotent retry/body mismatch/crash/read-after-delete semantics. | **Open** | No delete route in `routers/memories.py:77–235`; no tombstone mutation; no per-memory operation table/schema/status route; create-only Redis idempotency is in `create_memory:83–115`. Current `PgVectorStore.delete` only clears vectors (`:124–141`). |
| **Immediate retrieval suppression:** authoritative tombstone blocks vector, FTS, hydration, hot cache, context and other registered paths at the contractually defined acknowledgement point. | **Partial** | Existing SQL excludes already-deleted rows (`pgvector_store.py:21–27`, `full_text.py:21–27`, `repository.py:43–50`, `hot_cache.py:27–35`), and stale hot-cache IDs are rehydrated. But no operation creates the tombstone, no context-level tombstone proof is present, and no delete-vs-search/cache race test exists. |
| **G4 deletion fan-out:** resumable, idempotent per-memory purge/redaction across Postgres, vector, Redis sorted-set/object keys, FTS/index, artifacts, exports, analytics and configured derived stores. | **Open** for per-memory; **partial** for org-only | Org saga has store stages (`org_deletion.py:354–405`) and physical org purge (`:104–110`), but all receipts are job/store/scope=`org` (`000037:354–372`, `org_deletion_receipts.py:68–95`). No per-memory task or resource-scoped fan-out was found. |
| **Deletion certificate/replay safety/legal hold:** per-memory receipts/failures/retries/certificate; tombstone/version fence prevents delayed worker/queue/replay resurrection; hold blocks physical purge but never retrieval. | **Open** for per-memory; **partial** for org deletion | Org hold blocking and org certificate exist (`org_deletion.py:309–327,407–430`), but no per-memory certificate or tombstone/version fence. Evidence contract explicitly requires replay tombstone checks (`10-evidence-contract.md:9–15`); current org receipts do not establish it. Current legal holds are org-only (`000037:283–305`). |
| **G6 typed lifecycle:** append-only observations and rebuildable authorized active projection; complete provenance/source/actor/hash/times/retention/hold/model identity; explicit quarantine review/promote/correct/supersede/expire/delete transitions. | **Partial** local lifecycle; **open** target criterion | Hash, temporal fields, statuses, PII quarantine and supersession exist (`000014`, `000017`, `persist.py:89–141`, `conflict/persist.py:84–136`), but request/persistence is generic and hard-codes `source='user_provided'` (`schemas/memories.py:22–57`, `persist.py:99–115`), no append-only observations/projection or review/promote API exists. |
| **Hard expiry:** ordinary vector, FTS, final hydration and hot-cache retrieval exclude not-yet-valid and expired intervals, while historical conflict detection has an explicit non-user mode. | **Resolved in code; partial in acceptance evidence** | PR #936 `125fde3` added predicates and `include_expired` separation. Current exact SQL and unit contract test are listed above. No DB-backed time-boundary matrix or hosted/profile artifact was found; do not promote beyond local hardening. |
| **Release evidence:** cross-tenant/resource negative matrix; delete/search/cache races; vector/FTS/cache/artifact/export purge; queue retry/replay/restart; holds/clear; duplicate/body-mismatch; PII/audit privacy; expiry across all methods; backup/restore/mixed-version migration; at least one named profile end-to-end. | **Open** | Existing local isolation/quarantine/stale-row tests cover slices only. No per-memory deletion/race/replay/hold/certificate/restore tests were identified. The plan’s Gate 4 requires profile-specific deletion certificate and safe degradation (`implementation-plan.md:159–164`), and definition of done requires owner/profile/evidence artifacts (`:179–181`). |
| **Status promotion:** canonical ledger has source commit, test/recovery/hosted artifact, profile/dependencies, owner/date, limitations/review date. | **Open** | `00-status-and-evidence.md:5–13` defines this proof and `:21–35` keeps memory at shipped-local and typed lifecycle/deletion certification blocked. No accepted GAP-04 entry exists. |

## Merged PR assessment

### PR #934 — merged `393c8b7d24787531e8b9c522b22b3b258c4d8cff`

- Confirmed merged to `main` on 2026-10-06.
- Changed principal/token-agent enforcement, fail-closed middleware, idempotency package behavior, evidence relay validation, budget/provider failure mapping, CI/supply-chain material, and docs.
- The only memory-service file in its changed-file list is `services/memory/Dockerfile`; it did not change memory lifecycle routes, schema, read SQL, deletion worker, or memory tests.
- **Disposition:** no GAP-04 closure evidence. It supplies foundational G1/G2/evidence hardening context but not a memory operation/tombstone implementation.

### PR #936 — merged `125fde3da214649f319cb54e5f87b96f2ed3575c`

- Confirmed merged after #934 (`parent 393c8b7`) on 2026-10-06.
- Memory-relevant changes: `services/memory/app/read/full_text.py`, `read/hot_cache.py`, `read/repository.py`, `vectorstore/base.py`, `vectorstore/pgvector_store.py`, `dedup/service.py`; `services/memory/tests/unit/test_lifecycle_predicates_unit.py` added; dedup tests updated.
- Verified behavioral change: current-time `valid_from`/`valid_until` predicates are present on ordinary retrieval paths; `include_expired=True` is explicit only for write-time historical conflict candidates; tests assert the SQL contract and the dedup mode.
- PR #936 also touched evidence relay and architecture/gap docs, but those changes did not add per-memory deletion or typed lifecycle implementation. Current `18-gap-register.md:47–58` records temporal read fence hardening as partial and keeps typed lifecycle/provenance open.
- **Disposition:** one GAP-04 subgap (ordinary retrieval expiry fence) is code-level resolved; the overall gap and release acceptance remain open.

### PR #937 — merged `7298e5ee7982b926630566c88830c99650c8eb37`

- This is the audited target commit and clean `main`.
- Changed only `.github/scripts/check-search-index-limit-sync.sh`, `.github/scripts/web-smoke.sh`, `.github/workflows/ci.yml`, and `.github/workflows/web-deploy.yml`.
- **Disposition:** no GAP-04 runtime, schema, test, or documentation behavior change.

## Residual subgaps

1. **Contract/G0:** no accepted lifecycle authority matrix, owner/profile decision, state-transition table, retention/hold policy, or migration/rollback contract.
2. **Observation model:** no append-only source-event/observation ledger; no rebuildable projection; no source span/artifact reference; no processed time; no actor/purpose/trust envelope; no retention class; no per-memory hold state; no model/preprocessing identity.
3. **Attribution:** `insert_memory_session` hard-codes `user_provided` and omits `created_by_user`; worker/extracted origin may be misclassified.
4. **Review/promotion:** quarantine exclusion exists, but no authorized human/operator review, promote, correction, or appeal lifecycle.
5. **State transitions:** status vocabulary includes archived/merged/deleted but generic API transitions are absent; conflict escalation is not an authoritative review workflow.
6. **Operation semantics:** no durable per-memory operation ID/state, cancellation, status query, or operation-to-evidence linkage; create Redis idempotency is not sufficient.
7. **Tombstone semantics:** no public per-memory tombstone, immediate suppression point, resource-scoped authorization, or read-after-delete contract.
8. **Fan-out:** no per-memory worker for canonical content, vector, FTS/index, Redis sorted-set/object keys, object artifacts, ClickHouse/exports, or other profile-derived stores.
9. **Replay fencing:** no tombstone/version-fence check serialized with sink writes/replays for memory resources; delayed extraction/embedding/cache work could be a resurrection risk once a delete operation exists.
10. **Certificate:** org receipts/certificate are not a per-memory deletion certificate and cannot prove an individual resource is absent from every configured store.
11. **Hold semantics:** only org-scoped holds are implemented; per-memory hold policy and the rule that a held resource remains non-retrievable are not implemented as a memory lifecycle contract.
12. **Expiry evidence:** PR #936 fixed predicates, but only SQL-shape unit tests were found; DB-backed boundary and all deployed-path tests remain needed.
13. **Recovery:** no named profile demonstrates restore/replay/deletion behavior, measured RPO/RTO, mixed-version migration/backfill, or no resurrection after restore.
14. **Context boundary:** context assembly is provisional and must reject tombstoned/expired/quarantined content after authorized retrieval; a temporal SQL fence alone is not typed ContextEnvelope or end-to-end context proof.
15. **Evidence boundary:** evidence/outbox relay hardening from #934/#936 is partial; no accepted memory-operation/deletion event, acknowledgement class, redaction, sink, or profile recovery artifact closes GAP-005/GAP-011.

## Dependencies and shared-boundary ownership

- **G0 / architecture owner:** freeze state vocabulary, authority, source/trust labels, legal/retention semantics, operation/deletion contract, profile matrix, migration/rollback and acceptance evidence before new lifecycle schema/effects.
- **G1 Auth/Proxy + Memory:** every mutation needs verified principal, org/agent/resource scope, actor/purpose, anti-enumeration and fail-closed behavior. PR #934’s principal hardening is a prerequisite, not a memory closure.
- **G2 Idempotency/replay:** shared key/body-hash semantics and uncertain-commit/retry behavior must precede delete operations and worker replay. The create idempotency path cannot be reused without a durable operation contract.
- **G4 Evidence/Security + Platform:** operation and deletion events, redaction, outbox atomicity, relay/sink deduplication, tombstone fencing, poison/retry/watermarks, and certificate storage are cross-cutting prerequisites to “certified deletion.”
- **Memory owner:** canonical observation/projection, lifecycle transitions, tombstone transaction, per-memory fan-out and status API.
- **Context owner:** registered retrieval paths, ContextEnvelope, authorized candidate filtering, returned-hit scope/tombstone/expiry/quarantine checks, and approved quality degradation. Context is not lifecycle authority.
- **Worker/operations owner:** resumable fan-out, configured-store inventory, receipt/certificate generation, legal-hold behavior, restart/restore sequencing, and profile deployment evidence.
- **Data/privacy/legal owners:** source taxonomy, retention classes, per-memory/org hold scope, physical purge exceptions, redaction rules, and customer-visible completion semantics.
- **Postgres is target lifecycle authority;** Redis is cache/projection; vector/FTS/ClickHouse/object storage are projections/artifacts. This is canonical target ownership (`06-authority-and-data-ownership.md`), not proof that current runtime fully enforces it.
- **GAP overlap:** P0 GAP-005 owns end-to-end tenant isolation/deletion/evidence proof; P1 GAP-007 owns typed memory lifecycle/provenance; GAP-011 owns recovery. GAP-04 cannot be promoted independently while those shared gates are open.

## Exact next acceptance checks

1. **G0 artifact check:** a dated owner-approved contract/ADR/registry entry names the lifecycle authority, profile, compatibility/version, states/transitions, actor/source taxonomy, retention/legal hold, read-after-write/delete, idempotency/body mismatch, typed failures, evidence envelope, replay fence, migration/backfill/rollback, and review expiry.
2. **Schema/operation check:** integration test creates a memory operation with tenant-bound idempotency, durable operation ID, state transitions, body-mismatch conflict, retry/uncertain-commit behavior, and atomic tombstone+outbox. Verify operation-status query and no raw memory body in operation/evidence payloads.
3. **Authorization matrix:** cross-org, wrong-agent/resource, missing principal/purpose, deleted/held/quarantined target, and anti-enumeration cases deny with zero downstream side effects; verify RLS and service-boundary identity.
4. **Immediate suppression race:** acknowledge deletion only after the authoritative tombstone/suppression point; concurrently search vector/FTS/final hydration/hot cache/context and assert no returned hit after that point, including stale Redis IDs.
5. **Fan-out/certificate check:** exercise Postgres canonical row, vector, FTS/index, Redis sorted set/object keys, object artifact, ClickHouse/export/derived stores for the named profile; assert resumability, per-store receipt/status/error/retry, deterministic certificate, and no silent omission.
6. **Replay fence check:** queue delayed create/embed/cache/export/replay work before delete; delete; restart/retry every worker; assert no resurrection. Serialize tombstone/version check with sink write or reject writes older than the deletion fence.
7. **Hold check:** active hold blocks only physical purge where policy requires, never retrieval; clear hold and resume safely; record hold state in operation/certificate without exposing held content.
8. **Typed lifecycle check:** append source observations with actor/source/span/artifact/hash/observed/processed/valid times, retention/hold, model/embedding/preprocessing IDs; rebuild active projection; verify projection cannot widen visibility and extraction suggestions are untrusted.
9. **Review/state check:** quarantine never default-retrieves; authorized review can promote/reject/correct; supersede/merge/archive/expire/delete transitions are explicit, audited, idempotent, and tenant-scoped.
10. **Expiry check:** DB-backed boundary tests at `valid_from` and `valid_until` for vector, FTS, hydration, hot cache, context, and any future registered path; confirm historical conflict mode is unavailable to ordinary callers.
11. **Recovery check:** named deployment profile restores Postgres/outbox/memory stores/artifacts/ClickHouse policy/keys; reruns tombstone/deletion/replay negative tests; publishes measured RPO/RTO and migration/backfill reconciliation.
12. **Status promotion check:** update `00-status-and-evidence.md` with exact commit/config/dependency digests, reproducible CI/profile artifacts, owner/date, limitations and review date. Until this exists, retain lower maturity labels.

## Risks and uncertainties

- **Verified current code vs external topology:** this audit is bounded to the repository at `7298e5e`; no external deployment profile, customer retention policy, or independently accepted lifecycle was found. Their existence outside the repository is unknown, not disproven.
- **Org deletion coverage:** external stores and tables covered by the saga depend on configured topology and allowlists. The saga is substantial, but it is not evidence that every customer’s derived store/export is covered or replay-safe.
- **Source attribution risk:** hard-coded `user_provided` could assign incorrect trust/promotion semantics to extracted or agent-derived facts.
- **`include_expired` risk:** this is currently an internal conflict-detection escape hatch. A future caller must not expose it through user retrieval or context assembly; add capability/contract tests around the boundary.
- **Temporal evidence risk:** SQL-shape assertions can pass while wiring or transaction/runtime behavior differs; DB-backed expiry boundary tests and profile execution are still needed.
- **Migration risk:** converting mutable rows into observation/projection semantics requires expand/dual-write/backfill/verify/contract sequencing, mixed-version compatibility, resumability, and rollback/roll-forward criteria.
- **Privacy risk:** operation/evidence/certificate payloads must not copy raw memory bodies, embeddings, secrets, or unredacted PII.
- **Acceptance uncertainty:** no named owner approval, G0 exit artifact, hosted acceptance, recovery drill, or production deletion certificate was found. A merge commit alone is explicitly insufficient under the canonical ledger.

## Verification limitations

The checkout remained clean at the required commit before and after inspection (`git status --short --branch` showed `main...origin/main`; `HEAD=7298e5ee...`). A focused pytest attempt for `test_lifecycle_predicates_unit.py` and `test_dedup_service.py` was **blocked because pytest is not installed in the sandbox**. This report therefore claims source/test inspection and merged-history evidence, not a fresh test pass. The assigned memo records a prior focused memory run of 77 unit tests, but that historical result is not re-certified here and does not cover per-memory deletion.

## Final disposition

**Keep GAP-04 open.** Accept PR #936’s temporal read-fence change as a bounded local hardening disposition only. The next high-quality vertical slice remains: G0 contract acceptance → tenant-authorized per-memory tombstone + durable operation/outbox + immediate retrieval suppression → observable replay-safe per-store fan-out/certificate → typed observations/projection/review/expiry and named-profile recovery. Do not claim governed memory, GDPR erasure, deletion propagation, or production readiness from the current schema status values, local tests, org saga, or merged PRs alone.
