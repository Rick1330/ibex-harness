# G0 Test Matrix

**Status:** Planned evidence; no row is an acceptance decision by itself.

| Area | Unit evidence | Integration/E2E evidence | Negative cases | Acceptance signal |
|---|---|---|---|---|
| Principal binding | Parse/validate context; reject missing org, agent, authority, or expiry | Proxy → AuthService → Context/Memory correlation IDs | cross-org, cross-agent, expired proof, mismatched claim/header | fail-closed response and no downstream write |
| Policy snapshot | Digest, authority, epoch, freshness calculations | Auth-issued snapshot consumed by proxy/context | stale, unknown authority, digest mismatch | protected action denied with auditable reason |
| Idempotency | key scope and request-digest equality | crash/retry around durable record and side effect | same key/different body; pending lease expiry; uncertain outcome | one side effect, explicit replay/conflict/uncertified outcome |
| Evidence | JCS golden vectors; redaction allowlist; tombstone monotonicity | producer → relay → projection | secret, unclassified, stale fence, cross-tenant event | quarantine/no projection and stable digest |
| Memory ownership | Search mode and validity fence in both PgVector and in-memory store | write pipeline candidate load and supersession | wrong org, wrong agent, future/expired user read, historical internal read | candidate cannot cross agent; user path remains fenced |
| Retry semantics | operation retry table and state transitions | worker restart and external timeout | ambiguous external commit | no silent success; approved `202`/uncertified or reconciliation |
| Privacy/deletion | sanitizer field tests | delete/tombstone then replay/project | stale event after deletion | no resurrection and no sensitive projection |

## Required artifacts

Each row should link to a test result, fixture version, environment, and known limitations. The review record must distinguish **pass**, **not run**, **blocked**, and **not applicable**. A green test suite cannot close an owner decision without the named owner/reviewer and expiry.
