ALTER TABLE ibex.llm_traces
    DROP COLUMN IF EXISTS fallback_reason,
    DROP COLUMN IF EXISTS fallback_model,
    DROP COLUMN IF EXISTS original_model;
