# Security Invariants and Test Gates

**Status:** `specified`; invariant IDs are normative targets for implementation.

- **SEC-001 Tenant isolation:** no cross-org/resource read, write, existence leak, cache hit, vector result, analytics row, artifact, log, export, or deletion effect.
- **SEC-002 Verified principal:** missing, stale, mismatched, or caller-forged identity denies before downstream work.
- **SEC-003 Explicit authorization:** every route, method, tool, export, deletion, credential, and provider operation declares permission, role, ownership, and resource scope.
- **SEC-004 Fail closed:** auth, policy, budget integrity, tool registry, egress, secrets, deletion authority, and evidence integrity failures cannot become allow.
- **SEC-005 Untrusted context:** memory, repository, MCP, tool, web, and model text is data; it cannot override directives or create authority.
- **SEC-006 PII defense in depth:** deterministic and neural detection are imperfect; uncertain/high-impact content quarantines or redacts, and no non-detection proves absence.
- **SEC-007 Replay safety:** mutations are tenant-bound and idempotent; retries cannot duplicate authoritative effects.
- **SEC-008 Evidence privacy:** ordinary telemetry contains no raw secrets, tokens, unredacted PII, prompts, or memory bodies.
- **SEC-009 Deletion:** tombstones immediately suppress reads; fan-out is observable and legal hold is explicit.
- **SEC-010 Egress:** destination, DNS/IP, redirects, protocol, limits, credentials, and private-network exceptions are validated.

## Required gates

Cross-tenant matrix, RLS/connection-pool tests, Redis/vector/ClickHouse/object isolation, anti-enumeration, prompt-injection and poisoning corpus, tool replay/approval, SSRF, secret leakage, deletion/legal-hold, failover/chaos, and evidence crash/replay tests are release gates. A model classifier may strengthen a gate but cannot replace deterministic enforcement.
