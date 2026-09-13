-- Milestone 4.C.4: audit original vs fallback model on llm_traces (ADR-0077).
ALTER TABLE ibex.llm_traces
    ADD COLUMN IF NOT EXISTS original_model Nullable(String),
    ADD COLUMN IF NOT EXISTS fallback_model Nullable(String),
    ADD COLUMN IF NOT EXISTS fallback_reason LowCardinality(String) DEFAULT '';
