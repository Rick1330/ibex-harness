-- Milestone 2.4.1: sessions + immutable turn checkpoints (Phase 2 subset).
-- See ADR-0032. Fuller DATABASE_SCHEMA.md sessions model remains deferred.

CREATE TABLE ibex_core.sessions (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id               UUID NOT NULL
                         REFERENCES ibex_core.organizations(id)
                         ON DELETE CASCADE,
    agent_id             UUID NOT NULL,
    external_id          TEXT,
    status               TEXT NOT NULL DEFAULT 'active'
                         CHECK (status IN ('active', 'completed', 'abandoned', 'error')),
    model                TEXT NOT NULL,
    provider             TEXT NOT NULL,
    -- Composite FK (id, org_id) — SET NULL is impossible while org_id is NOT NULL;
    -- clear_session_directive_version() nulls the pointer before version DELETE.
    directive_version_id UUID,

    turn_count           INTEGER NOT NULL DEFAULT 0,
    total_input_tokens   BIGINT NOT NULL DEFAULT 0,
    total_output_tokens  BIGINT NOT NULL DEFAULT 0,
    total_latency_ms     BIGINT NOT NULL DEFAULT 0,

    last_extracted_turn  INTEGER NOT NULL DEFAULT 0,

    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at         TIMESTAMPTZ,
    deleted_at           TIMESTAMPTZ,

    UNIQUE (id, org_id),
    CONSTRAINT sessions_agent_org_fk
        FOREIGN KEY (agent_id, org_id)
        REFERENCES ibex_core.agents (id, org_id)
        ON DELETE CASCADE,
    CONSTRAINT sessions_directive_version_org_fk
        FOREIGN KEY (directive_version_id, org_id)
        REFERENCES ibex_core.directive_versions (id, org_id)
        ON DELETE RESTRICT
);

-- Client-supplied X-IBEX-Session-ID lookup (nullable; multiple NULLs allowed).
CREATE UNIQUE INDEX idx_sessions_org_agent_external_id
    ON ibex_core.sessions (org_id, agent_id, external_id)
    WHERE external_id IS NOT NULL;

CREATE TABLE ibex_core.checkpoints (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id          UUID NOT NULL,
    org_id              UUID NOT NULL
                        REFERENCES ibex_core.organizations(id)
                        ON DELETE CASCADE,
    agent_id            UUID NOT NULL,
    turn_index          INTEGER NOT NULL,
    request_id          TEXT NOT NULL,

    messages_hash       TEXT NOT NULL,
    input_tokens        INTEGER NOT NULL DEFAULT 0,
    output_tokens       INTEGER NOT NULL DEFAULT 0,
    model               TEXT NOT NULL,
    provider            TEXT NOT NULL,

    completion_hash     TEXT,
    latency_ms          INTEGER NOT NULL,
    provider_request_id TEXT,
    is_streaming        BOOLEAN NOT NULL DEFAULT false,
    is_complete         BOOLEAN NOT NULL DEFAULT true,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (session_id, turn_index),
    UNIQUE (id, org_id),
    CONSTRAINT checkpoints_session_org_fk
        FOREIGN KEY (session_id, org_id)
        REFERENCES ibex_core.sessions (id, org_id)
        ON DELETE CASCADE,
    CONSTRAINT checkpoints_agent_org_fk
        FOREIGN KEY (agent_id, org_id)
        REFERENCES ibex_core.agents (id, org_id)
        ON DELETE CASCADE,
    CONSTRAINT checkpoints_turn_index_nonneg CHECK (turn_index >= 0),
    CONSTRAINT checkpoints_latency_nonneg CHECK (latency_ms >= 0)
);

-- Phase 3 memory extraction worker: partial predicate encodes "has unextracted turns"
-- so the index only contains rows the worker needs (column-vs-column range scan is not used).
CREATE INDEX idx_sessions_agent_extraction
    ON ibex_core.sessions (agent_id, last_extracted_turn)
    WHERE status = 'completed'
      AND deleted_at IS NULL
      AND last_extracted_turn < turn_count;

CREATE INDEX idx_checkpoints_session_turn
    ON ibex_core.checkpoints (session_id, turn_index);

CREATE INDEX idx_sessions_org_agent
    ON ibex_core.sessions (org_id, agent_id)
    WHERE deleted_at IS NULL;

CREATE INDEX idx_sessions_org_status
    ON ibex_core.sessions (org_id, status)
    WHERE deleted_at IS NULL;

ALTER TABLE ibex_core.sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.sessions FORCE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.checkpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.checkpoints FORCE ROW LEVEL SECURITY;

CREATE POLICY sessions_isolation ON ibex_core.sessions
    USING (ibex_core.rls_org_visible(org_id));

CREATE POLICY checkpoints_isolation ON ibex_core.checkpoints
    USING (ibex_core.rls_org_visible(org_id));

GRANT SELECT, INSERT, UPDATE, DELETE ON ibex_core.sessions TO ibex_app;
-- Append-only checkpoints: SELECT+INSERT only. Parent CASCADE DELETE runs as table owner.
GRANT SELECT, INSERT ON ibex_core.checkpoints TO ibex_app;
GRANT USAGE ON SCHEMA ibex_core TO ibex_app;

CREATE OR REPLACE FUNCTION ibex_core.reject_checkpoint_update()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ibex_core, pg_temp
AS $$
BEGIN
    RAISE EXCEPTION 'checkpoints is append-only';
END;
$$;

REVOKE ALL ON FUNCTION ibex_core.reject_checkpoint_update() FROM PUBLIC;

CREATE TRIGGER checkpoints_immutable
    BEFORE UPDATE ON ibex_core.checkpoints
    FOR EACH ROW EXECUTE FUNCTION ibex_core.reject_checkpoint_update();

CREATE TRIGGER sessions_updated_at
    BEFORE UPDATE ON ibex_core.sessions
    FOR EACH ROW EXECUTE FUNCTION ibex_core.set_updated_at();

-- Preserve SET NULL semantics for directive_version_id while using a composite org-scoped FK.
CREATE OR REPLACE FUNCTION ibex_core.clear_session_directive_version()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ibex_core, pg_temp
AS $$
BEGIN
    UPDATE ibex_core.sessions
    SET directive_version_id = NULL
    WHERE directive_version_id = OLD.id;
    RETURN OLD;
END;
$$;

REVOKE ALL ON FUNCTION ibex_core.clear_session_directive_version() FROM PUBLIC;

CREATE TRIGGER directive_versions_clear_sessions
    BEFORE DELETE ON ibex_core.directive_versions
    FOR EACH ROW EXECUTE FUNCTION ibex_core.clear_session_directive_version();
