-- request-idempotency-core.v1: Release removes the caller's claimed row.
-- This is a privilege correction only; table shape and concurrency semantics are unchanged.
GRANT DELETE ON ibex_core.idempotency_ledger TO ibex_app;
GRANT DELETE ON ibex_core.idempotency_ledger TO ibex_service;
