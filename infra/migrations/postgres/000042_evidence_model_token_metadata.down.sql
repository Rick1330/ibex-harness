ALTER TABLE ibex_core.evidence_runs
    DROP CONSTRAINT IF EXISTS evidence_runs_model_id_safe,
    DROP CONSTRAINT IF EXISTS evidence_runs_input_tokens_bounded,
    DROP CONSTRAINT IF EXISTS evidence_runs_output_tokens_bounded,
    DROP CONSTRAINT IF EXISTS evidence_runs_total_tokens_bounded,
    DROP CONSTRAINT IF EXISTS evidence_runs_total_tokens_consistent,
    DROP COLUMN IF EXISTS model_id,
    DROP COLUMN IF EXISTS input_tokens,
    DROP COLUMN IF EXISTS output_tokens,
    DROP COLUMN IF EXISTS total_tokens;
