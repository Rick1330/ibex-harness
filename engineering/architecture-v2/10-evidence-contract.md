# Evidence Contract

**Status:** `specified`; existing outbox coverage is partial until the ledger proves otherwise.

## Event envelope

Every evidence event includes event ID, event type/schema version, org/principal/resource, run/request/trace IDs, policy epoch, operation/reservation IDs, source/artifact references, redaction classification, timestamps, outcome, degradation/fallback reason, and retention/legal-hold class.

## Durability

For events required before acknowledgement, the transaction writes canonical state and the outbox atomically. Relay is at-least-once; consumers deduplicate by event ID and projection version. Before applying any replayed event, the consumer checks the authoritative resource tombstone and skips events for deleted resources; a projection or cache cannot resurrect deleted state. For each replay sink, serialize the tombstone check and write with deletion, or require the sink to reject writes older than a deletion/version fence. Deletion is complete only after no in-flight replay can restore stale state. Replay is supported from canonical state or retained outbox. ClickHouse and OTel are projections/exporters, not the only durable authority.

## Minimum events

Admission/deny, reservation/release/reconcile, provider attempt/usage, context manifest, memory operation, MCP/tool call, approval, deletion, model decision, artifact promotion, and operator action.

## Privacy

Raw prompts, memory bodies, secrets, tokens, embeddings, and unredacted PII do not enter ordinary logs, metrics, or evidence payloads. Large sensitive bodies use access-controlled redacted artifacts and stable references. Query/export paths enforce tenant scope and retention.

## Capture completeness (operator read model)

`operator.evidence.summary.v1` reports what the plane can prove. It deliberately does **not** call a run "certified":
an `evidence_runs` row holds no digest of its own, so the only digest in the plane is
`evidence_outbox.payload_digest`, per event.

The contract states four separate facts:

- **Capture completeness** — `evidence_runs.completeness`. `complete` means the record holds the full capture for the
  run. `partial`, `sampled`, `late`, `redacted`, `expired`, `deleted`, and `simulated` each name why it does not.
  A sampled or partial window is never extrapolated to a population figure.
- **Operation outcome** — `evidence_runs.status` (`ok` / `error`). Evidence of a failed operation is still complete
  evidence, so the outcome is a separate axis and does not lower the capture count.
- **Relay delivery** — `evidence_outbox.delivery_status`. Reported at organization level, because the outbox carries no
  run reference. A complete capture whose event has not reached its sink is shown as exactly that, not as a success.
- **Retention context** — the effective `org_capture_policies.mode` and whether a `legal_holds` row is active. A hold
  preserves data; it does not make a record more complete.

Sources for the rule: OpenTelemetry's trace-completeness semantics (a trace is complete only when all spans are
collected; incompleteness is either intentional sampling or a collection error, and non-probability sampling must not be
extrapolated) and in-toto's attestation validation (completeness is checked against declared requirements, never
assumed). Both are recorded here as design precedent, not as a compliance claim.

Out of scope until a separate read model exists: field-level redaction detail. The Console renders the Redaction tab as
explicitly unavailable rather than with fixtures; tombstones, deletion receipts, and audit continuity are covered by
`operator.evidence.deletions.v1`.

## Deletion evidence (operator read model)

`operator.evidence.deletions.v1` answers the three questions a deletion record exists for, and keeps them apart:

- **What was tombstoned.** `memory_lifecycle_outbox` deletion events (`forgotten`, `expired`, `purged`) in the window,
  and whether each was delivered. `memories.tombstoned` is the terminal visibility fence — tombstones win in every
  retrieval mode — and is reported as a current count, not a window count.
- **Did every store confirm the erasure.** `org_deletion_jobs` plus `deletion_store_receipts`: one receipt per deployed
  store, `verified` only when the worker proved absence. A `hold_blocked` job is a legal hold doing its job, not a
  failure. Erasure is a distributed transaction, not a `DELETE`, and a deletion you cannot evidence is, to an auditor, a
  deletion that did not happen.
- **Is the audit chain intact.** `privacy_audit_ledger` continuity: `seq` has no gaps and every `prev_hash` equals the
  previous `row_hash`. This is the append-only property only. Re-deriving `row_hash` from the payload is the
  `privacy-audit-verify` CLI's job; duplicating the canonicalisation in the API would create a second, divergent
  implementation. Verifiable logs draw the same line between consistency and inclusion proofs (Trillian).

Ledger payload, hold reasons, and memory content are never projected: the contract is counts, statuses, timestamps, and
hashes.

Tombstone background: a delete can race an offline replica, which is why stores keep a timestamped marker and a grace
window (Cassandra's `gc_grace_seconds`) so a returning replica cannot resurrect “zombie” data. Our `tombstoned` flag and
`lifecycle_revision` are that fence; the outbox is how the fence reaches every sink, and this contract reports whether it
did.
