-- 000071 makes `tokens.prefix` unique. That index cannot be built while two
-- rows share a prefix, and `CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS`
-- would then either fail with a one-line duplicate-key error or, worse, accept
-- an INVALID index left behind by an interrupted build and report success with
-- the invariant unenforced. This file runs first and refuses, by name, both
-- states.
--
-- Separate from 000071 for the same reason 000067 is separate from 000066:
-- 000071 must stay a single statement so CREATE INDEX CONCURRENTLY runs outside
-- an implicit transaction.
--
-- Why the invariant: `auth_find_token_by_prefix` resolves a bearer by prefix
-- alone and returns exactly one row. Two organizations sharing a prefix make
-- the older tenant's bearer resolve to the newer tenant's row, so the older
-- tenant is denied authentication. Same-organization duplicates are less
-- severe but still leave rows no reader can reach.

-- ================================================================
-- 1. No duplicate prefixes
-- ================================================================
DO $$
DECLARE
    v_offenders   text;
    v_dup_prefix  bigint;
    v_cross_org   bigint;
BEGIN
    SELECT COUNT(*) INTO v_dup_prefix
    FROM (SELECT t.prefix FROM ibex_core.tokens t GROUP BY t.prefix HAVING COUNT(*) > 1) d;

    SELECT COUNT(*) INTO v_cross_org
    FROM (
        SELECT t.prefix
        FROM ibex_core.tokens t
        GROUP BY t.prefix
        HAVING COUNT(DISTINCT t.org_id) > 1
    ) d;

    IF v_dup_prefix > 0 THEN
        SELECT string_agg(format('%s (%s rows, %s orgs)', d.prefix, d.n_rows, d.n_orgs), '; ')
        INTO v_offenders
        FROM (
            SELECT t.prefix, COUNT(*) AS n_rows, COUNT(DISTINCT t.org_id) AS n_orgs
            FROM ibex_core.tokens t
            GROUP BY t.prefix
            HAVING COUNT(*) > 1
            ORDER BY COUNT(*) DESC, t.prefix
            LIMIT 10
        ) d;

        RAISE EXCEPTION
            'tokens.prefix must be unique, but % prefix value(s) repeat (first 10: %). % prefix value(s) are shared by more than one organization, where auth_find_token_by_prefix returns one tenant the row of another. Repair before re-running: keep the row the reader selects for each prefix (newest, not revoked, not expired) and revoke or delete the others, or reissue them with fresh prefixes',
            v_dup_prefix, v_offenders, v_cross_org;
    END IF;
END;
$$;

-- ================================================================
-- 2. No invalid or non-unique index wearing the target name
-- ================================================================
-- 000071 uses IF NOT EXISTS so a dev down/up cycle is idempotent. That makes a
-- same-named index an implicit success: refuse anything that is not a valid,
-- unique, non-partial index on ibex_core.tokens (prefix).
DO $$
DECLARE
    v_indisvalid boolean;
    v_indisunique boolean;
    v_indpred     text;
BEGIN
    SELECT i.indisvalid, i.indisunique, pg_get_expr(i.indpred, i.indrelid)
      INTO v_indisvalid, v_indisunique, v_indpred
      FROM pg_index i
      JOIN pg_class c ON c.oid = i.indexrelid
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'ibex_core'
       AND c.relname = 'idx_tokens_prefix_unique';

    IF NOT FOUND THEN
        RETURN;
    END IF;

    IF NOT v_indisvalid THEN
        RAISE EXCEPTION
            'ibex_core.idx_tokens_prefix_unique exists but is INVALID (an interrupted CONCURRENTLY build). The unique prefix invariant would be silently unenforced. Repair with: DROP INDEX CONCURRENTLY ibex_core.idx_tokens_prefix_unique; then re-run this migration';
    END IF;

    IF NOT v_indisunique OR v_indpred IS NOT NULL THEN
        RAISE EXCEPTION
            'ibex_core.idx_tokens_prefix_unique exists but is not a plain unique index (unique flag %, predicate %); drop it and re-run so 000071 builds the unique index',
            v_indisunique, v_indpred;
    END IF;
END;
$$;
