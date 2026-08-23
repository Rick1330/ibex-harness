ALTER TABLE ibex_core.organizations
    ADD COLUMN embedding_profile TEXT NOT NULL DEFAULT 'cpu'
        CHECK (embedding_profile IN ('cpu', 'gpu', 'hosted')),
    ADD COLUMN embedding_dim INTEGER NOT NULL DEFAULT 384
        CHECK (embedding_dim > 0),
    ADD COLUMN embedding_model_id TEXT NOT NULL DEFAULT 'all-MiniLM-L6-v2'
        CHECK (length(trim(embedding_model_id)) > 0);
