-- Milestone 4.P.4: immutable per-call usage facts for cost governance.
-- No TTL: billing/financial retention (SECURITY.md section 11). Ops purge policy is explicit.
-- Dual to Postgres ibex_billing (rate cards / budgets / enforcement decisions).
-- Requires x-multi-statement=true on the migrate DSN.
-- Note: do not put semicolons in comments (multi-statement splitter).

CREATE TABLE IF NOT EXISTS ibex.usage_facts
(
    request_id            String,
    org_id                UUID,
    agent_id              UUID,
    provider              LowCardinality(String),
    model                 LowCardinality(String),
    original_model        Nullable(String),
    fallback_model        Nullable(String),
    fallback_reason       LowCardinality(String) DEFAULT '',

    input_tokens          UInt32,
    output_tokens         UInt32,
    total_tokens          UInt32,

    estimated_cost_cents  Int64,
    actual_cost_cents     Nullable(Int64),
    rate_card_version     String,
    completeness          LowCardinality(String) DEFAULT 'partial',

    occurred_at           DateTime64(3, 'UTC'),
    event_date            Date MATERIALIZED toDate(occurred_at)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(event_date)
ORDER BY (org_id, agent_id, occurred_at)
SETTINGS index_granularity = 8192;
