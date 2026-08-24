-- Milestone 2.5.G5.M1: memories foundation with bi-temporal validity columns.
-- CREATE (not ALTER): ibex_core.memories did not exist prior to this migration.
-- Embedding / HNSW / multi-label join tables are deferred to Phase 3.1.1 / G5.M2–M3.
-- See ADR-0047.

CREATE TABLE ibex_core.memories (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           UUID NOT NULL
                     REFERENCES ibex_core.organizations(id)
                     ON DELETE RESTRICT,
    agent_id         UUID NOT NULL,
    session_id       UUID,
    created_by_user  UUID
                     REFERENCES ibex_core.users(id)
                     ON DELETE SET NULL,

    -- Content
    content          TEXT NOT NULL,
    content_hash     TEXT NOT NULL,
    content_tokens   INTEGER NOT NULL,

    -- Classification / lifecycle (scalar category retained for G5.M2 compat)
    category         TEXT NOT NULL DEFAULT 'factual'
                     CHECK (category IN (
                         'factual',
                         'preference',
                         'behavioral',
                         'episodic',
                         'procedural'
                     )),
    status           TEXT NOT NULL DEFAULT 'active'
                     CHECK (status IN (
                         'active',
                         'superseded',
                         'merged_into',
                         'archived',
                         'quarantined',
                         'deleted'
                     )),
    deleted_at       TIMESTAMPTZ,

    -- Temporal validity (world time + observation time)
    -- Interval is half-open [valid_from, valid_until); NULL valid_until = still open.
    valid_from       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_until      TIMESTAMPTZ,
    observed_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (id, org_id),

    CONSTRAINT memories_agent_org_fk
        FOREIGN KEY (agent_id, org_id)
        REFERENCES ibex_core.agents (id, org_id)
        ON DELETE CASCADE,

    -- MATCH SIMPLE: NULL session_id skips the FK check. Composite ON DELETE SET NULL
    -- would also null org_id (NOT NULL), so session clears run via trigger below.
    CONSTRAINT memories_session_org_fk
        FOREIGN KEY (session_id, org_id)
        REFERENCES ibex_core.sessions (id, org_id),

    CONSTRAINT memories_content_not_empty CHECK (length(content) > 0),
    CONSTRAINT memories_content_max CHECK (octet_length(content) <= 10000),
    CONSTRAINT memories_content_hash_not_empty CHECK (length(content_hash) > 0),
    CONSTRAINT memories_content_tokens_nonneg CHECK (content_tokens >= 0),
    CONSTRAINT memories_valid_interval_chk
        CHECK (valid_until IS NULL OR valid_until > valid_from)
);

CREATE INDEX idx_memories_agent_active
    ON ibex_core.memories (org_id, agent_id)
    WHERE status = 'active' AND deleted_at IS NULL;

CREATE INDEX idx_memories_content_hash
    ON ibex_core.memories (org_id, agent_id, content_hash);

-- Preserve nullable session_id while using a composite org-scoped FK.
CREATE OR REPLACE FUNCTION ibex_core.clear_memory_session_id()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ibex_core, pg_temp
AS $$
BEGIN
    UPDATE ibex_core.memories
    SET session_id = NULL
    WHERE session_id = OLD.id;
    RETURN OLD;
END;
$$;

REVOKE ALL ON FUNCTION ibex_core.clear_memory_session_id() FROM PUBLIC;

CREATE TRIGGER sessions_clear_memory_session_id
    BEFORE DELETE ON ibex_core.sessions
    FOR EACH ROW EXECUTE FUNCTION ibex_core.clear_memory_session_id();

ALTER TABLE ibex_core.memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.memories FORCE ROW LEVEL SECURITY;

CREATE POLICY memories_isolation ON ibex_core.memories
    USING (ibex_core.rls_org_visible(org_id));

GRANT SELECT, INSERT, UPDATE, DELETE ON ibex_core.memories TO ibex_app;
GRANT USAGE ON SCHEMA ibex_core TO ibex_app;

CREATE TRIGGER memories_updated_at
    BEFORE UPDATE ON ibex_core.memories
    FOR EACH ROW EXECUTE FUNCTION ibex_core.set_updated_at();
