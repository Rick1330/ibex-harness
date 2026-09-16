DROP TABLE IF EXISTS ibex.evidence_assembly_metrics;
DROP TABLE IF EXISTS ibex.evidence_spans;

ALTER TABLE ibex.llm_traces
    DROP COLUMN IF EXISTS completeness,
    DROP COLUMN IF EXISTS score_schema,
    DROP COLUMN IF EXISTS context_assembly_ms,
    DROP COLUMN IF EXISTS directive_version_id,
    DROP COLUMN IF EXISTS root_span_id,
    DROP COLUMN IF EXISTS trace_id;
