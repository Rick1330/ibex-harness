-- 000067 changes no state; it only asserts that 000066's concurrent index is
-- not INVALID. The down mirrors the assertion so a rollback reports a broken
-- index rather than silently leaving it.
DO $$
DECLARE index_valid boolean;
BEGIN
    SELECT i.indisvalid INTO index_valid
    FROM pg_index i
    WHERE i.indexrelid = to_regclass('ibex_core.idx_tokens_prefix');
    IF index_valid IS FALSE THEN
        RAISE EXCEPTION
            'idx_tokens_prefix is INVALID during rollback. '
            'Repair with: DROP INDEX CONCURRENTLY ibex_core.idx_tokens_prefix; '
            'then re-run `migrate up`.';
    END IF;
END;
$$;
