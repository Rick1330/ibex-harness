-- Milestone 4.A.3: agent description + default provider/model for Track C routing.
-- New columns inherit existing agents_isolation RLS (no policy changes).
-- CHECK constraints are NOT VALID so ADD skips a full-table scan; VALIDATE in a
-- follow-up migration once the columns have been live.

ALTER TABLE ibex_core.agents
    ADD COLUMN IF NOT EXISTS description TEXT,
    ADD COLUMN IF NOT EXISTS default_provider TEXT,
    ADD COLUMN IF NOT EXISTS default_model TEXT;

ALTER TABLE ibex_core.agents
    DROP CONSTRAINT IF EXISTS agents_description_max,
    DROP CONSTRAINT IF EXISTS agents_default_provider_max,
    DROP CONSTRAINT IF EXISTS agents_default_model_max;

ALTER TABLE ibex_core.agents
    ADD CONSTRAINT agents_description_max
        CHECK (description IS NULL OR octet_length(description) <= 4096) NOT VALID,
    ADD CONSTRAINT agents_default_provider_max
        CHECK (default_provider IS NULL OR (
            char_length(default_provider) BETWEEN 1 AND 64
        )) NOT VALID,
    ADD CONSTRAINT agents_default_model_max
        CHECK (default_model IS NULL OR (
            char_length(default_model) BETWEEN 1 AND 128
        )) NOT VALID;
