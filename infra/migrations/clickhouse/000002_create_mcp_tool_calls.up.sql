-- Phase 2.5 MCP tool-call audit (m2.5.G6.M1 / ADR-0050). No memory content columns.
-- Requires x-multi-statement=true on the migrate DSN.
CREATE DATABASE IF NOT EXISTS ibex;

CREATE TABLE IF NOT EXISTS ibex.mcp_tool_calls
(
    request_id   String,
    org_id       UUID,
    agent_id     Nullable(UUID),
    tool_name    LowCardinality(String),
    latency_ms   UInt32,
    success      Bool,
    error_code   LowCardinality(String),
    requested_at DateTime64(3, 'UTC'),

    event_date   Date MATERIALIZED toDate(requested_at)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(event_date)
ORDER BY (org_id, requested_at, request_id)
TTL event_date + INTERVAL 90 DAY
SETTINGS index_granularity = 8192;
