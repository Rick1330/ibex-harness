ALTER TABLE ibex_core.organizations
    DROP COLUMN IF EXISTS embedding_model_id,
    DROP COLUMN IF EXISTS embedding_dim,
    DROP COLUMN IF EXISTS embedding_profile;
