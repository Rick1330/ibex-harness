-- Operator directive reads: the list pages directives by (updated_at, id) inside
-- an org, and the detail counts sessions that resolved to one directive's
-- versions inside a window. Neither path had an index of that shape.
-- CONCURRENTLY, one index per file body, matching 000048-000052.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_directives_org_updated_at
    ON ibex_core.directives (org_id, updated_at DESC, id DESC);
