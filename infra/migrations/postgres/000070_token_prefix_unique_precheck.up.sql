-- 000071 makes `tokens.prefix` unique. That index cannot be built while two
-- rows share a prefix, and `CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS`
-- would then either fail with a one-line duplicate-key error or, worse, accept
-- an INVALID index left behind by an interrupted build and report success with
-- the invariant unenforced. This file runs first and refuses, by name, every
-- state that would leave the invariant unenforced.
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
            'tokens.prefix must be unique, but % prefix value(s) repeat (first 10: %). % prefix value(s) are shared by more than one organization, where auth_find_token_by_prefix returns one tenant the row of another. Repair before re-running: for each repeated prefix keep one row and delete the others, or reissue the duplicates with fresh prefixes. Revoking is not a repair: a revoked row keeps its prefix and still blocks the unique index',
            v_dup_prefix, v_offenders, v_cross_org;
    END IF;
END;
$$;

-- ================================================================
-- 2. No invalid, wrong-shaped, or non-index relation wearing the target name
-- ================================================================
-- 000071 uses IF NOT EXISTS so a dev down/up cycle is idempotent. That makes a
-- same-named relation an implicit success: PostgreSQL resolves the IF NOT EXISTS
-- check against pg_class, so a table, view or sequence with that name makes
-- 000071 skip its build with a NOTICE, and `migrate up` reports success with the
-- invariant unenforced. Refuse anything that is not a valid, ready, unique,
-- non-partial index whose only key column is ibex_core.tokens.prefix.
DO $$
DECLARE
    v_relkind     "char";
    v_indisvalid  boolean;
    v_indisready  boolean;
    v_indisunique boolean;
    v_indpred     text;
    v_indrelid    oid;
    v_indnkeyatts smallint;
    v_indkey0     smallint;
BEGIN
    SELECT c.relkind
      INTO v_relkind
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'ibex_core'
       AND c.relname = 'idx_tokens_prefix_unique';

    IF NOT FOUND THEN
        RETURN;
    END IF;

    IF v_relkind <> 'i' THEN
        RAISE EXCEPTION
            'ibex_core.idx_tokens_prefix_unique exists but is not an index (pg_class.relkind = %). 000071 skips its build for any relation wearing that name, so the unique prefix invariant would stay unenforced. Rename or drop the relation, then re-run this migration',
            v_relkind;
    END IF;

    SELECT i.indisvalid, i.indisready, i.indisunique,
           pg_get_expr(i.indpred, i.indrelid),
           i.indrelid, i.indnkeyatts, i.indkey[0]
      INTO v_indisvalid, v_indisready, v_indisunique, v_indpred,
           v_indrelid, v_indnkeyatts, v_indkey0
      FROM pg_index i
     WHERE i.indexrelid = to_regclass('ibex_core.idx_tokens_prefix_unique');

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'ibex_core.idx_tokens_prefix_unique is an index with no pg_index row; the catalog is inconsistent. Drop the relation and re-run this migration';
    END IF;

    IF NOT v_indisvalid OR NOT v_indisready THEN
        RAISE EXCEPTION
            'ibex_core.idx_tokens_prefix_unique exists but is INVALID (an interrupted CONCURRENTLY build). The unique prefix invariant would be silently unenforced. Repair with: DROP INDEX CONCURRENTLY ibex_core.idx_tokens_prefix_unique; then re-run this migration';
    END IF;

    IF NOT v_indisunique OR v_indpred IS NOT NULL THEN
        RAISE EXCEPTION
            'ibex_core.idx_tokens_prefix_unique exists but is not a plain unique index (unique flag %, predicate %); drop it and re-run so 000071 builds the unique index',
            v_indisunique, v_indpred;
    END IF;

    -- A unique index over another table, over more than prefix, or over an
    -- expression does not enforce what the reader relies on: (prefix, org_id) is
    -- unique while one prefix still repeats across organizations, and an
    -- expression index compares something other than the raw prefix.
    IF v_indrelid <> 'ibex_core.tokens'::regclass
       OR v_indnkeyatts <> 1
       OR v_indkey0 IS DISTINCT FROM (
            SELECT a.attnum
              FROM pg_attribute a
             WHERE a.attrelid = 'ibex_core.tokens'::regclass
               AND a.attname = 'prefix'
               AND NOT a.attisdropped) THEN
        RAISE EXCEPTION
            'ibex_core.idx_tokens_prefix_unique exists but does not index exactly ibex_core.tokens (prefix) (indexed table oid %, key columns %, first key attnum %); drop it and re-run so 000071 builds the unique index',
            v_indrelid, v_indnkeyatts, v_indkey0;
    END IF;
END;
$$;
