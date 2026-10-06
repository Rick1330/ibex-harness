# Documentation-First Roadmap and Gates

**Status:** `specified` implementation sequence.

## Gates

- **G0 Documentation/contract freeze:** status ledger, authority matrix, registry, trust labels, dependency matrix, and ADRs. No new boundary or side effect before exit.
- **G1 Principal/tenant invariants:** propagation, explicit authorization, RLS, cache/search/analytics isolation, anti-enumeration, and fail-closed tests.
- **G2 Errors/idempotency:** transport mappings, body hashes, claim/finalize/replay/TTL/crash behavior.
- **G3 Provider/admission:** immutable manifests, token fit, reservations, limits, reconciliation, and no-provider-after-deny.
- **G4 Evidence MVP:** envelope, outbox, relay, dedupe/replay, redaction, retention, restore, and minimum event coverage.
- **G5 Request/streaming slice:** one measured provider path, separate Responses semantics, stable unsupported errors, and accepted latency budget.
- **G6 Typed memory/context:** provenance, trust, PII/quarantine, operation status, deletion tombstone, authorized retrieval, typed manifest, and safe fallback.
- **G7 Read-only operator/MCP:** versioned API, Console, diagnostics, read-only MCP, descriptor hashes, limits, cancellation, and stdio policy.
- **G8 Operations/recovery:** profiles, backups, restore, migrations, drain, capacity, incidents, key rotation, and measured RPO/RTO.
- **G9 Governed side effects:** operation intent/receipt, approval, exact tool descriptors, egress, credentials, isolated execution, and reconciliation.
- **G10 Advisory intelligence:** benchmark, pin, calibrate, shadow, canary, rollback, and resource/isolation gates. No model authority.
- **G11 Deferred extensions:** graph, A2A, managed cloud, marketplace, broad guardrails, coding sandbox, and extra providers require separate evidence and ADR.

## Prohibited before G0

No new service/package boundary, database lifecycle, provider adapter, write-capable tool, budget-enforcement change, or model integration may be treated as implementation-ready before the documentation and contract freeze is accepted.

The initial review packet was tracked by issue #935 and ADR-0084. Issue #935 was closed by PR #936; neither that merge nor closure records G0 owner acceptance. The subsequent eight-area source audit and docs-only preparation are tracked by [issue #939](https://github.com/Rick1330/ibex-harness/issues/939), with the complete [pre-G0 synthesis and workplan](20-pre-g0-gap-synthesis-and-workplan.md), [proposal-only owner decision worksheet](21-g0-owner-decision-recommendations.md), and [source-audit index](../research/ibex-preflight-2026-10/README.md). These documents are review inputs only; they do not exit G0 or authorize gated runtime work.

## G0 exit criteria

G0 exits only when named auth/policy, contract, evidence/security, deployment, and other applicable domain owners approve the packet and `00-status-and-evidence.md` records the exact source commit, profile/dependencies, artifact/digests, limitations, decision owner/date, and review/expiry date. The accepted packet must resolve PrincipalContext field requiredness, PolicySnapshot authority/epoch, RunEnvelope lineage, transport trust, idempotency/replay/conflict, budget admission scope, provider capability/support state, memory attribution/retention/hold, context fallback/session history, MCP write disposition, evidence acknowledgement/redaction, relay/sink dedupe and tombstone fencing, recovery objectives, and compatibility/migration rules. A decision log with unassigned role names, a PR merge, or an issue closure does not satisfy this gate.

Until formal G0 exit, permitted work is limited to read-only inventory, documentation, owner-decision preparation, review evidence, and contract/test-matrix preparation. No new boundary, schema/lifecycle, provider adapter, budget-enforcement change, model integration, or write-capable effect is authorized. After exit, implementation must follow the work dependencies and independent acceptance gates in the synthesis; any eligible seam still needs its relevant G1–G8 gate and named-profile evidence. G9 control-plane execution remains downstream of G0–G8, and G11 extensions remain deferred.
