-- Persist only structurally safe model identity and provider-reported token totals.
-- Content-bearing request/response data remains outside the evidence metadata row.
ALTER TABLE ibex_core.evidence_runs
    ADD COLUMN model_id TEXT,
    ADD COLUMN input_tokens BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN output_tokens BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN total_tokens BIGINT NOT NULL DEFAULT 0,
    ADD CONSTRAINT evidence_runs_model_id_safe
        CHECK (model_id IS NULL OR model_id ~ '^[A-Za-z0-9._:+/-]{1,128}$'),
    ADD CONSTRAINT evidence_runs_input_tokens_bounded
        CHECK (input_tokens BETWEEN 0 AND 1000000000000),
    ADD CONSTRAINT evidence_runs_output_tokens_bounded
        CHECK (output_tokens BETWEEN 0 AND 1000000000000),
    ADD CONSTRAINT evidence_runs_total_tokens_bounded
        CHECK (total_tokens BETWEEN 0 AND 1000000000000),
    ADD CONSTRAINT evidence_runs_total_tokens_consistent
        CHECK (total_tokens >= input_tokens + output_tokens);
