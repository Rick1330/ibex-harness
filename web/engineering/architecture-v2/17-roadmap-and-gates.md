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

The first review packet is tracked by issue #935 and ADR-0084. It proposes the token-bound agent rule, protected-profile verifier readiness, tenant-bound idempotency semantics, evidence acknowledgement/redaction, and a one-sink relay/recovery pilot boundary. This reference records the packet location only; it is not a G0 exit or an authorization to bypass the remaining gates.

## G0 exit criteria for issue #935

G0 exits only when named auth/policy, contract, evidence/security, and deployment owners approve the packet and `00-status-and-evidence.md` records the exact source commit, profile/dependencies, evidence artifact, limitations, owner/date, and review date. The accepted packet must resolve PrincipalContext field requiredness, PolicySnapshot authority/epoch, RunEnvelope lineage, transport trust, idempotency/replay/conflict, redaction, acknowledgement/uncertified behavior, relay/sink dedupe and tombstone fencing, and compatibility/migration rules.

Until then, the only permitted work on issue #935 is documentation, review evidence, and contract/test-matrix preparation. After exit, the first eligible implementation seams are limited to one additive proxy-to-context PrincipalContext mapping, one evidence persistence/idempotency/redaction slice, and one operational relay/sink/recovery pilot; each still requires a separate owner/status-ledger decision and its applicable G1/G2/G4 gate. None of these eligibility statements authorize a durable RunEnvelope, atomic budget reservation, provider expansion, typed memory lifecycle, MCP governance, or control-plane side effects.
