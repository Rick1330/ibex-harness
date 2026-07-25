-- Phase 2 llm_traces (m2.5.1). No prompt/completion content columns.
-- Requires x-multi-statement=true on the migrate DSN.
CREATE DATABASE IF NOT EXISTS ibex;

CREATE TABLE IF NOT EXISTS ibex.llm_traces
(
    request_id           String,
    org_id               UUID,
    agent_id             UUID,
    session_id           Nullable(UUID),
    checkpoint_id        Nullable(UUID),

    model                LowCardinality(String),
    provider             LowCardinality(String),
    is_streaming         Bool,

    input_tokens         UInt32,
    output_tokens        UInt32,
    total_tokens         UInt32,

    auth_latency_ms      UInt16,
    directive_latency_ms UInt16,
    provider_ttfb_ms     UInt32,
    total_latency_ms     UInt32,

    status_code          UInt16,
    is_complete          Bool,
    error_code           LowCardinality(String),

    requested_at         DateTime64(3, 'UTC'),
    completed_at         DateTime64(3, 'UTC'),

    event_date           Date MATERIALIZED toDate(requested_at)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(event_date)
ORDER BY (org_id, agent_id, requested_at)
TTL event_date + INTERVAL 90 DAY
SETTINGS index_granularity = 8192;
