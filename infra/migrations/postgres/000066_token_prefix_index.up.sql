-- P0-06 follow-up: `auth_find_token_by_prefix` validates tokens on every
-- request and filters `tokens.prefix`, which has no index. Without one, every
-- validation is a sequential scan of the token table.
--
-- Single statement on purpose: golang-migrate sends one file through one
-- ExecContext, and a multi-statement string is an implicit transaction, in
-- which CREATE INDEX CONCURRENTLY is illegal (same pattern as 000059).
-- CONCURRENTLY keeps token writes unblocked; a failed build leaves an INVALID
-- index — drop it and retry.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tokens_prefix
    ON ibex_core.tokens (prefix);
