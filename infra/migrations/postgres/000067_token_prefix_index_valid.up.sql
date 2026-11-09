-- 000066 builds idx_tokens_prefix CONCURRENTLY. An interrupted build leaves
-- the index present but INVALID, and 000066's IF NOT EXISTS would accept it on
-- the next `migrate up`, leaving the token lookup without a usable index.
--
-- Refuse to continue and say how to repair it. A missing index is not a
-- failure: the lookup still works with a sequential scan, and 000066 is the
-- migration that creates it.
--
-- Separate from 000066 because 000066 must stay a single statement for
-- CREATE INDEX CONCURRENTLY to run outside an implicit transaction.
DO $$
DECLARE index_valid boolean;
BEGIN
    SELECT i.indisvalid INTO index_valid
    FROM pg_index i
    WHERE i.indexrelid = to_regclass('ibex_core.idx_tokens_prefix');
    IF index_valid IS FALSE THEN
        RAISE EXCEPTION
            'idx_tokens_prefix is INVALID (interrupted CONCURRENTLY build). '
            'Repair with: DROP INDEX CONCURRENTLY ibex_core.idx_tokens_prefix; '
            'then re-run `migrate up`.';
    END IF;
END;
$$;
