# D2 local performance notes (contract-tested)

**Scope:** metadata-only operator trace list/detail against PostgreSQL evidence plane.  
**Not a hosted P6 claim.** Thresholds below are local stop-conditions for this PR.

## Query budgets

| Path | Bound | Local stop-condition |
|---|---|---|
| List SQL `statement_timeout` | 3000ms | Fail closed as `SERVICE_DEGRADED` |
| Max page size | 100 | Validation error |
| Max time range | 7 days | Validation error |
| Cursor TTL | 15 minutes | Invalid cursor |
| Console BFF fetch timeout | 5000ms | Operator API error |

## Expected local shape

- List: filter-before-page + count + outbox publication enrichment per page.
- Detail: run row + optional child tables (spans/assembly/candidates/directive/tools), each bounded.
- Prefer additive index `(org_id, started_at DESC, trace_id DESC)` if list p95 rises under realistic volume; not required to invent hosted p99 here.

## Evidence

- Unit: `services/api/tests/unit/test_operator_traces.py`
- Integration (when DSN available): `services/api/tests/integration/test_operator_traces_rls.py`
- Console codec: `services/console/tests/live-query.test.ts`
- Hosted AuthService four-role matrix and measured staging p50/p95/p99 remain `blocked_external` in `infra/assurance/p6/d2-residual-register.json`.
