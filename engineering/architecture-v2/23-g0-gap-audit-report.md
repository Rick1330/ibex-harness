# G0 / GAP-001–012 Audit Report

**Repository:** `Rick1330/ibex-harness`
**Audited checkout:** `main` at `e633e48983da4bb21f552343e89632172270cb1a` (`feat(evidence): add ClickHouse relay sink pilot (#968)`)
**Audit date:** 2026-10-13
**Profile:** local Podman development/test stack

## Executive conclusion

The repository is **not fully G0-accepted as an implementation or production-readiness milestone**. The dated G0 decision record accepts the **contract shape and safety semantics only**, while the runtime seams remain provisional. The current implementation and the status ledger support that narrower conclusion.

There is a material documentation contradiction that should be resolved before using the architecture packet as an approval record:

- `21-g0-owner-decision-record.md:3,78` says G0 was accepted by Rick1330 on 2026-10-10 and the review window closed early.
- `00-status-and-evidence.md:3,31` also describes five contract shapes as accepted.
- `18-gap-register.md:26,61` still says G0/GAP-001–003 remain proposed, have no named-owner acceptance artifact, and that Rick1330's acting assignment is provisional pending confirmation by 2026-10-22.
- `03-contract-registry.md:47` says the recorded choices remain a review baseline rather than G0 acceptance, while `03-contract-registry.md:137` says the five shapes are accepted.

Until the owner/reviewer and status records are reconciled, the correct operational label is **contract-shape accepted in one dated artifact; GAP-001–003 and runtime implementation remain open/provisional in the controlling gap register**.

## 2026-10-20 addendum

The owner/reviewer contradiction above is now reconciled in the controlling documents: `00-status-and-evidence.md`, `03-contract-registry.md`, `18-gap-register.md`, and `21-g0-owner-decision-record.md` all record the same 2026-10-10 contract-shape acceptance by Rick1330 as acting owner, with no independent reviewer named and a 2026-11-10 review date. This addendum does not promote any runtime GAP.

Updates since the original audit:

- **GAP-004:** the proxy enforcement-overhead target is ratified at p99 ≤20 ms for the warm, mock-provider local/protected profile. PR #1018 merged the blocking same-runner relative Go benchmark gate (warm-path means, 20% tolerance) on 2026-10-20. No hosted/reference p99 measurement exists, so GAP-004 remains open.
- **GAP-009:** the read-only operator gateway is `shipped-local` and default-off; PolicySnapshot resource/action evaluation, durable rich-field audit, and hosted evidence remain open.
- **GAP-011:** the evidence relay daemon (#1002) is deployable but default-off; ClickHouse remains a G4-gated pilot and hosted/HA recovery evidence is absent.
- **Decisions 4–8:** `18-gap-register.md` now records explicit pending/bounded dispositions. No contract aliasing, missing package fields, `required_evidence=false` gate, or hosted Responses support is inferred.

The audit conclusion is unchanged: the repository is not G0-approved for runtime, hosted, HA, or production readiness, and no GAP is closed by this addendum.

## Verification performed

`make check` passed at the audited checkout:

- roadmap status check passed;
- Markdown lint: 173 files, 0 issues;
- gitleaks: no leaks found;
- all pinned tool versions matched;
- Podman stack readiness passed for PostgreSQL, Redis, ClickHouse, MinIO, and both object-store buckets.

This is repository/tooling readiness evidence only. It is not evidence of hosted HA, production support, or G1–G4 completion.

## G0 five open questions

The five explicit follow-up decisions in `18-gap-register.md:63-69` are **not all resolved**.

| Question | Assessment | Evidence |
|---|---|---|
| Production evidence producer metadata and relay readiness | **Unresolved** | `18-gap-register.md:65`; `services/proxy/internal/http/session/evidence.go:91-118` constructs `RunInput` without `RedactionClass` or `TombstoneFence`. The store therefore defaults to unclassified/fenceless metadata and the relay rejects/poisons it. No producer sanitizer or authoritative producer fence source is wired. |
| Memory historical-mode trust boundary | **Partially addressed, not resolved** | `18-gap-register.md:66`; `SearchMode` is still an in-process `PgVectorStore.search` parameter. The conflict loader rejects ordinary user mode, but a direct internal caller can request historical mode. A dedicated capability-bearing write-path adapter is not present. |
| PolicySnapshot authority identity and freshness | **Resolved in the dated G0 contract record, but stale/contradictory elsewhere** | `21-g0-owner-decision-record.md:17-18,28-44` selects AuthService authority and records 60s/30s/5m bounds plus 5s clock skew. `18-gap-register.md:67` still presents the exact authority/freshness/stale behavior as an open owner decision. |
| HTTP mapping for evidence acknowledgement | **Unresolved** | `18-gap-register.md:68` explicitly says exact HTTP/error codes are not chosen. The recommended candidate is `503 EVIDENCE_UNAVAILABLE`, with profile-approved `202 outcome=uncertified` only after durable retry state; no accepted golden response mapping is implemented. |
| Acting-owner confirmation | **Contradictory, not safely closed** | `21-g0-owner-decision-record.md:24,78` records Rick1330 as acting owner and says acceptance occurred. `18-gap-register.md:26,43,57,61,69` says individual confirmation remains pending through 2026-10-22. This requires an explicit reconciliation record, not inference. |

Therefore, the answer to “were all five open G0 questions answered?” is **no**. One is clearly unresolved, one is partially addressed but lacks the required capability boundary, one is answered only by the dated decision record but contradicted by the GAP register, one remains explicitly unresolved, and the owner confirmation state conflicts across records.

## G0 contract-shape findings

### PrincipalContext

The additive schema and local mapping seam exist:

- `packages/proto/proto/ibex/auth/v1/principal_context.proto:9-26` defines fields 1–14.
- `packages/proto/proto/ibex/context/v1/context.proto:33-39` carries `PrincipalContext` additively on `AssembleContextRequest`.
- `packages/proto/principal_context_contract_test.go:9-25` checks stable field numbers/names.
- `services/proxy/internal/http/principal_context.go:36-137` maps verified AuthService data, rejects missing bindings, rejects cross-org bindings, and rejects token-agent mismatch.
- `services/proxy/internal/http/principal_context_test.go:13-115` covers user/service identity, correlation/timestamps, mismatch, missing bindings, and cross-org rejection.

This is good **local additive seam evidence**, but it is not repo-wide propagation, signed propagation, downstream authorization, hosted evidence, or production acceptance.

### Evidence redaction and acknowledgement

The relay has meaningful fail-closed hardening:

- `packages/evidenceoutbox/types.go:10-17,28-34,139-153` defines producer-declared redaction class and tombstone fence fields.
- `packages/evidenceoutbox/store.go:252-267,657-713` validates fences and injects producer metadata into serialized payloads.
- `packages/evidenceoutbox/relay.go:138-183,222-259` rejects unclassified, prohibited, unsupported, missing/invalid-fence, digest-invalid, and non-fence-aware deliveries; permanent failures enter the poison path.
- `packages/evidenceoutbox/relay_unit_test.go:126-182,232-249,350-383` covers acknowledgement-loss replay, poison thresholds, and unsafe metadata.
- The PostgreSQL integration evidence recorded in `18-gap-register.md:41-45` covers local persistence, replay, tenant RLS, role restrictions, and poison transitions.

However, the producer class is only a declaration. The relay does **not** inspect or sanitize payload content. The production session producer explicitly omits both class and fence (`services/proxy/internal/http/session/evidence.go:102-118`), so current rows cannot safely reach projection. This is intentionally safer than silent projection, but it is not an end-to-end evidence acknowledgement implementation.

### JCS / canonicalization

The architecture contract requires RFC 8785-compatible JCS bytes (`contracts/jcs-canonicalization.md:5-18`) and provides four vectors (`contracts/jcs-test-vectors.json:1-29`). Those are contract fixtures, not proof of an evidence-envelope JCS implementation.

The existing implementations are different canonicalization contracts:

- `packages/privacyaudit/canonical.go:4-20` deliberately matches PostgreSQL `jsonb::text` for the privacy hash chain, including PostgreSQL key ordering and spacing.
- `packages/session/hash.go:17-25` hashes Go `encoding/json` output for checkpoint messages.

No reviewed RFC 8785/JCS implementation is wired into the evidence outbox payload digest path. This remains a material gap for the evidence contract if JCS is required for evidence digests rather than only documented as a future contract.

### ClickHouse relay sink and fencing

The sink is correctly labeled as a **non-production pilot**:

- `packages/evidenceoutbox/clickhousesink/sink.go:1-3,23-27` treats ClickHouse as a projection and requires an injected authoritative fence checker.
- `packages/evidenceoutbox/clickhousesink/sink.go:82-109` checks the fence, performs tenant-scoped dedupe, then inserts.
- `packages/evidenceoutbox/clickhousesink/sink.go:91-93` explicitly admits that the check and insert are not one cross-store atomic lifecycle transaction.
- `infra/migrations/clickhouse/000006_evidence_events.up.sql:1-23` uses `ReplacingMergeTree`, tenant/event/sequence ordering, and a 90-day TTL.
- `packages/evidenceoutbox/clickhousesink/sink_test.go:58-118` covers required fence checker, tenant predicate, fence failure, insertion, and invalid fence.
- `packages/evidenceoutbox/clickhousesink/sink_integration_test.go:23-103` is opt-in and skips unless `CLICKHOUSE_TEST_NATIVE_DSN` is set.

This is partial local pilot evidence, not production sink certification, authoritative lifecycle integration, atomic delete-vs-project fencing, or hosted/HA recovery evidence.

## GAP-001 through GAP-012 disposition

The GAP register does not mark any gap as closed or accepted. The current disposition is:

| Gap | Current status | Audit interpretation |
|---|---|---|
| GAP-001 | **Open / contradictory status records** | Documentation claims conflict; G0 ledger reconciliation is incomplete. |
| GAP-002 | **Open** | Authority matrix is documented in part, but runtime boundaries and named confirmation are not fully closed. |
| GAP-003 | **Open** | Registry exists, but several rows remain proposed/design-only and runtime compatibility evidence is incomplete. |
| GAP-004 | **Open** | Latency/deadline claims remain conflicting or unmeasured; status ledger also calls the context deadline discrepancy open. |
| GAP-005 | **Open / non-accepted** | Tenant/deletion/evidence path lacks sanitizer proof, authoritative lifecycle-table integration, and full-store end-to-end evidence. |
| GAP-006 | **Open** | No universally accepted durable operation ledger and reconciliation implementation. |
| GAP-007 | **Open / non-accepted** | Search-mode hardening exists, but typed lifecycle/provenance/checkpoints, capability isolation, direct agent predicate protection, and in-memory parity remain. |
| GAP-008 | **Open** | Provider capability/alias/streaming/usage semantics remain fragmented; required manifest/conformance matrix is not accepted. |
| GAP-009 | **Open / partial hardening** | Protected rate limiting is more fail-closed, but audit durability and operator boundaries remain open. |
| GAP-010 | **Design-intent / deferred to G10** | No runtime DecisionService/model registry/calibration/benchmark acceptance evidence. |
| GAP-011 | **Open / non-accepted** | Backup/restore, hosted/HA recovery, lifecycle authority, and production ClickHouse evidence remain incomplete. |
| GAP-012 | **Deferred by design** | Expansion is intentionally deferred until core gates pass; it is not a closed implementation gap. |

## Recommended next actions

1. **Reconcile the owner record immediately:** choose whether `21-g0-owner-decision-record.md` supersedes the historical pending language in `18-gap-register.md` and `03-contract-registry.md`; update all three documents consistently with the same owner, reviewer, acceptance date, expiry, and scope.
2. **Do not enable production evidence relay yet:** keep the current fail-closed behavior. Add a reviewed sanitizer/content-class proof and an authoritative resource-lifecycle fence source to the session producer before labeling rows `metadata`.
3. **Choose and test the acknowledgement mapping:** record the final `EVIDENCE_UNAVAILABLE`/`uncertified` status and response schema, then add golden HTTP tests for failed, unknown, durable, replay, and degraded-profile outcomes.
4. **Implement JCS where the evidence contract requires it:** use a reviewed RFC 8785-compatible library and run the repository vectors from `contracts/jcs-test-vectors.json`; do not conflate this with PostgreSQL JSONB canonicalization or checkpoint hashing.
5. **Replace the in-process historical mode with a dedicated internal adapter/capability boundary** before expanding historical conflict retrieval.
6. **Keep all production claims bounded:** current evidence supports local Podman readiness and focused local tests only, not hosted/HA, production support, exactly-once effects, or G1–G4 completion.
