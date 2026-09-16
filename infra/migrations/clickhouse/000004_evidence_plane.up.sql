-- Milestone 4.P.2: evidence-plane ClickHouse projections.
-- Dual-write window: legacy ibex.llm_traces remains the aggregate row;
-- new columns + companion tables carry nested span / metrics identity.
-- Write-path failure policy: FAIL-OPEN (unchanged from Phase 2) — CH down
-- must not block chat completions; drops are logged/metric'd only.

ALTER TABLE ibex.llm_traces
    ADD COLUMN IF NOT EXISTS trace_id String DEFAULT '',
    ADD COLUMN IF NOT EXISTS root_span_id String DEFAULT '',
    ADD COLUMN IF NOT EXISTS directive_version_id Nullable(UUID),
    ADD COLUMN IF NOT EXISTS context_assembly_ms UInt32 DEFAULT 0,
    ADD COLUMN IF NOT EXISTS score_schema LowCardinality(String) DEFAULT '',
    ADD COLUMN IF NOT EXISTS completeness LowCardinality(String) DEFAULT 'partial';

CREATE TABLE IF NOT EXISTS ibex.evidence_spans
(
    event_id             UUID,
    org_id               UUID,
    agent_id             Nullable(UUID),
    session_id           Nullable(UUID),
    checkpoint_id        Nullable(UUID),
    request_id           String,
    trace_id             String,
    span_id              String,
    parent_span_id       String,
    operation_kind       LowCardinality(String),
    status               LowCardinality(String),
    error_code           LowCardinality(String),
    schema_version       LowCardinality(String),
    aggregate_seq        UInt64,
    started_at           DateTime64(3, 'UTC'),
    ended_at             DateTime64(3, 'UTC'),
    event_date           Date MATERIALIZED toDate(started_at)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(event_date)
ORDER BY (org_id, trace_id, span_id, started_at)
TTL event_date + INTERVAL 90 DAY
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS ibex.evidence_assembly_metrics
(
    org_id                      UUID,
    request_id                  String,
    trace_id                    String,
    span_id                     String,
    budget_calculation_ms       UInt32,
    directive_load_ms           UInt32,
    hot_memory_retrieval_ms     UInt32,
    cold_memory_retrieval_ms    UInt32,
    ranking_ms                  UInt32,
    packing_ms                  UInt32,
    formatting_ms               UInt32,
    total_ms                    UInt32,
    candidates_evaluated        UInt32,
    recorded_at                 DateTime64(3, 'UTC'),
    event_date                  Date MATERIALIZED toDate(recorded_at)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(event_date)
ORDER BY (org_id, request_id, recorded_at)
TTL event_date + INTERVAL 90 DAY
SETTINGS index_granularity = 8192;
