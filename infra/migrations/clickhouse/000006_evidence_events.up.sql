-- Round 3 evidence relay pilot. This is a projection, never an authority.
CREATE DATABASE IF NOT EXISTS ibex;

CREATE TABLE IF NOT EXISTS ibex.evidence_events
(
    org_id           UUID,
    event_id         UUID,
    aggregate_id     String,
    aggregate_seq    Int64,
    schema_version   LowCardinality(String),
    event_type       LowCardinality(String),
    redaction_class  LowCardinality(String),
    resource_type    LowCardinality(String),
    resource_id      String,
    resource_version Int64,
    payload          String,
    received_at      DateTime64(3, 'UTC'),
    event_date       Date MATERIALIZED toDate(received_at)
)
ENGINE = ReplacingMergeTree(received_at)
PARTITION BY toYYYYMM(event_date)
ORDER BY (org_id, event_id, aggregate_seq)
TTL event_date + INTERVAL 90 DAY
SETTINGS index_granularity = 8192;
