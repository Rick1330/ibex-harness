ALTER TABLE ibex_core.agents
    DROP CONSTRAINT IF EXISTS agents_description_max,
    DROP CONSTRAINT IF EXISTS agents_default_provider_max,
    DROP CONSTRAINT IF EXISTS agents_default_model_max;

ALTER TABLE ibex_core.agents
    DROP COLUMN IF EXISTS description,
    DROP COLUMN IF EXISTS default_provider,
    DROP COLUMN IF EXISTS default_model;
