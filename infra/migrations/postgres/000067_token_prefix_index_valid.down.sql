-- A down must not raise before the index cleanup. 000067 changes no state; its
-- down drops the index it guarded so the next `migrate up` (000066) rebuilds a
-- fresh, valid one. 000066's down is idempotent and will find it already gone.
DROP INDEX CONCURRENTLY IF EXISTS ibex_core.idx_tokens_prefix;
