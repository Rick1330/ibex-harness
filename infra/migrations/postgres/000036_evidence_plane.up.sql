-- Milestone 4.P.2: canonical evidence plane + transactional outbox + session_events.
-- session_events was previously DATABASE_SCHEMA-only; this introduces the applied table
-- with evidence-plane linkage columns (trace_id, span_id, request_id, checkpoint_id).
-- Partitioning from the schema sketch is deferred (single table + indexes) — see milestone MDX.
-- RLS uses shared ibex_core.rls_org_visible(org_id) (000009).

-- ================================================================
-- SESSION EVENTS (append-only conversation / raw-payload log)
-- ================================================================
CREATE TABLE ibex_core.session_events (
    id              BIGSERIAL PRIMARY KEY,
    session_id      UUID NOT NULL,
    org_id          UUID NOT NULL
                    REFERENCES ibex_core.organizations(id)
                    ON DELETE CASCADE,
    sequence_number INTEGER NOT NULL,
    event_type      TEXT NOT NULL
                    CHECK (event_type IN (
                        'session_started',
                        'session_completed',
                        'session_failed',
                        'session_suspended',
                        'session_resumed',
                        'checkpoint_created',
                        'inference_request',
                        'inference_response',
                        'memory_read',
                        'memory_written',
                        'tool_called',
                        'tool_completed',
                        'tool_failed',
                        'directive_updated',
                        'loop_detected',
                        'error_occurred',
                        'evidence_span',
                        'evidence_assembly',
                        'evidence_archived'
                    )),
    data            JSONB NOT NULL DEFAULT '{}'::jsonb,
    archived_to     TEXT,
    -- Evidence-plane linkage (4.P.2)
    trace_id        TEXT,
    span_id         TEXT,
    request_id      TEXT,
    checkpoint_id   UUID,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (session_id, sequence_number),
    CONSTRAINT session_events_session_org_fk
        FOREIGN KEY (session_id, org_id)
        REFERENCES ibex_core.sessions (id, org_id)
        ON DELETE CASCADE
);

CREATE INDEX idx_session_events_session_seq
    ON ibex_core.session_events (session_id, sequence_number);
CREATE INDEX idx_session_events_org_created
    ON ibex_core.session_events (org_id, created_at DESC);
CREATE INDEX idx_session_events_trace
    ON ibex_core.session_events (org_id, trace_id)
    WHERE trace_id IS NOT NULL;
CREATE INDEX idx_session_events_request
    ON ibex_core.session_events (org_id, request_id)
    WHERE request_id IS NOT NULL;

ALTER TABLE ibex_core.session_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.session_events FORCE ROW LEVEL SECURITY;

CREATE POLICY session_events_isolation ON ibex_core.session_events
    USING (ibex_core.rls_org_visible(org_id));

GRANT SELECT, INSERT ON ibex_core.session_events TO ibex_app;
GRANT USAGE, SELECT ON SEQUENCE ibex_core.session_events_id_seq TO ibex_app;

-- ================================================================
-- EVIDENCE RUNS (one aggregate per request / OTel trace)
-- ================================================================
CREATE TABLE ibex_core.evidence_runs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL
                        REFERENCES ibex_core.organizations(id)
                        ON DELETE CASCADE,
    agent_id            UUID,
    session_id          UUID,
    request_id          TEXT NOT NULL,
    trace_id            TEXT NOT NULL,
    checkpoint_id       UUID,
    turn_id             INTEGER,
    schema_version      TEXT NOT NULL DEFAULT 'evidence.v1', -- NOSONAR
    completeness        TEXT NOT NULL DEFAULT 'partial'
                        CHECK (completeness IN (
                            'complete', 'partial', 'sampled', 'late',
                            'redacted', 'expired', 'deleted', 'simulated'
                        )),
    status              TEXT NOT NULL DEFAULT 'ok',
    error_code          TEXT,
    capture_mode        TEXT NOT NULL DEFAULT 'metadata',
    sample_decision     TEXT NOT NULL DEFAULT 'sampled',
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at            TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (id, org_id),
    UNIQUE (org_id, request_id),
    UNIQUE (org_id, trace_id, request_id)
);

CREATE INDEX idx_evidence_runs_org_trace
    ON ibex_core.evidence_runs (org_id, trace_id);
CREATE INDEX idx_evidence_runs_org_session
    ON ibex_core.evidence_runs (org_id, session_id)
    WHERE session_id IS NOT NULL;

ALTER TABLE ibex_core.evidence_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.evidence_runs FORCE ROW LEVEL SECURITY;

CREATE POLICY evidence_runs_isolation ON ibex_core.evidence_runs
    USING (ibex_core.rls_org_visible(org_id));

GRANT SELECT, INSERT, UPDATE, DELETE ON ibex_core.evidence_runs TO ibex_app;

-- ================================================================
-- EVIDENCE SPANS (nested OTel-compatible span identity)
-- ================================================================
CREATE TABLE ibex_core.evidence_spans (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL
                        REFERENCES ibex_core.organizations(id)
                        ON DELETE CASCADE,
    run_id              UUID NOT NULL,
    trace_id            TEXT NOT NULL,
    span_id             TEXT NOT NULL,
    parent_span_id      TEXT,
    request_id          TEXT NOT NULL,
    session_id          UUID,
    checkpoint_id       UUID,
    operation_kind      TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'ok',
    error_code          TEXT,
    attributes          JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at            TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (org_id, trace_id, span_id),
    CONSTRAINT evidence_spans_run_org_fk
        FOREIGN KEY (run_id, org_id)
        REFERENCES ibex_core.evidence_runs (id, org_id)
        ON DELETE CASCADE
);

CREATE INDEX idx_evidence_spans_run
    ON ibex_core.evidence_spans (run_id);
CREATE INDEX idx_evidence_spans_parent
    ON ibex_core.evidence_spans (org_id, trace_id, parent_span_id);

ALTER TABLE ibex_core.evidence_spans ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.evidence_spans FORCE ROW LEVEL SECURITY;

CREATE POLICY evidence_spans_isolation ON ibex_core.evidence_spans
    USING (ibex_core.rls_org_visible(org_id));

GRANT SELECT, INSERT, UPDATE, DELETE ON ibex_core.evidence_spans TO ibex_app;

-- ================================================================
-- EVIDENCE EVENTS (immutable event identity within a span)
-- ================================================================
CREATE TABLE ibex_core.evidence_events (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL
                        REFERENCES ibex_core.organizations(id)
                        ON DELETE CASCADE,
    run_id              UUID NOT NULL,
    span_id             TEXT NOT NULL,
    trace_id            TEXT NOT NULL,
    request_id          TEXT NOT NULL,
    event_name          TEXT NOT NULL,
    schema_version      TEXT NOT NULL DEFAULT 'evidence.v1', -- NOSONAR
    attributes          JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT evidence_events_run_org_fk
        FOREIGN KEY (run_id, org_id)
        REFERENCES ibex_core.evidence_runs (id, org_id)
        ON DELETE CASCADE
);

CREATE INDEX idx_evidence_events_run
    ON ibex_core.evidence_events (run_id, occurred_at);

ALTER TABLE ibex_core.evidence_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.evidence_events FORCE ROW LEVEL SECURITY;

CREATE POLICY evidence_events_isolation ON ibex_core.evidence_events
    USING (ibex_core.rls_org_visible(org_id));

GRANT SELECT, INSERT, UPDATE, DELETE ON ibex_core.evidence_events TO ibex_app;

-- ================================================================
-- ASSEMBLY METRICS / SCORE / DIRECTIVE / TOOL CONTRACTS
-- ================================================================
CREATE TABLE ibex_core.evidence_assembly_metrics (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                      UUID NOT NULL
                                REFERENCES ibex_core.organizations(id)
                                ON DELETE CASCADE,
    run_id                      UUID NOT NULL,
    request_id                  TEXT NOT NULL,
    trace_id                    TEXT NOT NULL,
    span_id                     TEXT,
    budget_calculation_ms       INTEGER NOT NULL DEFAULT 0
                                CHECK (budget_calculation_ms >= 0),
    directive_load_ms           INTEGER NOT NULL DEFAULT 0
                                CHECK (directive_load_ms >= 0),
    hot_memory_retrieval_ms     INTEGER NOT NULL DEFAULT 0
                                CHECK (hot_memory_retrieval_ms >= 0),
    cold_memory_retrieval_ms    INTEGER NOT NULL DEFAULT 0
                                CHECK (cold_memory_retrieval_ms >= 0),
    ranking_ms                  INTEGER NOT NULL DEFAULT 0
                                CHECK (ranking_ms >= 0),
    packing_ms                  INTEGER NOT NULL DEFAULT 0
                                CHECK (packing_ms >= 0),
    formatting_ms               INTEGER NOT NULL DEFAULT 0
                                CHECK (formatting_ms >= 0),
    total_ms                    INTEGER NOT NULL DEFAULT 0
                                CHECK (total_ms >= 0),
    candidates_evaluated        INTEGER NOT NULL DEFAULT 0
                                CHECK (candidates_evaluated >= 0),
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (org_id, request_id),
    CONSTRAINT evidence_assembly_metrics_run_org_fk
        FOREIGN KEY (run_id, org_id)
        REFERENCES ibex_core.evidence_runs (id, org_id)
        ON DELETE CASCADE
);

ALTER TABLE ibex_core.evidence_assembly_metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.evidence_assembly_metrics FORCE ROW LEVEL SECURITY;

CREATE POLICY evidence_assembly_metrics_isolation ON ibex_core.evidence_assembly_metrics
    USING (ibex_core.rls_org_visible(org_id));

GRANT SELECT, INSERT, UPDATE, DELETE ON ibex_core.evidence_assembly_metrics TO ibex_app;

CREATE TABLE ibex_core.evidence_score_candidates (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL
                        REFERENCES ibex_core.organizations(id)
                        ON DELETE CASCADE,
    run_id              UUID NOT NULL,
    request_id          TEXT NOT NULL,
    trace_id            TEXT NOT NULL,
    memory_id           UUID NOT NULL,
    retrieval_rank      INTEGER NOT NULL
                        CHECK (retrieval_rank >= 0),
    final_rank          INTEGER
                        CHECK (final_rank IS NULL OR final_rank >= 0),
    delta_rank          INTEGER,
    similarity          DOUBLE PRECISION,
    confidence          DOUBLE PRECISION
                        CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    composite_score     DOUBLE PRECISION,
    score_schema        TEXT NOT NULL DEFAULT 'interim_v1',
    score_components    JSONB NOT NULL DEFAULT '{}'::jsonb,
    exclusion           TEXT NOT NULL DEFAULT 'included',
    token_estimate      INTEGER
                        CHECK (token_estimate IS NULL OR token_estimate >= 0),
    category            TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT evidence_score_candidates_run_org_fk
        FOREIGN KEY (run_id, org_id)
        REFERENCES ibex_core.evidence_runs (id, org_id)
        ON DELETE CASCADE
);

CREATE INDEX idx_evidence_score_candidates_request
    ON ibex_core.evidence_score_candidates (org_id, request_id);

ALTER TABLE ibex_core.evidence_score_candidates ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.evidence_score_candidates FORCE ROW LEVEL SECURITY;

CREATE POLICY evidence_score_candidates_isolation ON ibex_core.evidence_score_candidates
    USING (ibex_core.rls_org_visible(org_id));

GRANT SELECT, INSERT, UPDATE, DELETE ON ibex_core.evidence_score_candidates TO ibex_app;

CREATE TABLE ibex_core.evidence_directive_snapshots (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                  UUID NOT NULL
                            REFERENCES ibex_core.organizations(id)
                            ON DELETE CASCADE,
    run_id                  UUID NOT NULL,
    request_id              TEXT NOT NULL,
    trace_id                TEXT NOT NULL,
    directive_version_id    UUID,
    content_hash            TEXT,
    schema_version          TEXT NOT NULL DEFAULT 'evidence.v1', -- NOSONAR
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (org_id, request_id),
    CONSTRAINT evidence_directive_snapshots_run_org_fk
        FOREIGN KEY (run_id, org_id)
        REFERENCES ibex_core.evidence_runs (id, org_id)
        ON DELETE CASCADE
);

ALTER TABLE ibex_core.evidence_directive_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.evidence_directive_snapshots FORCE ROW LEVEL SECURITY;

CREATE POLICY evidence_directive_snapshots_isolation ON ibex_core.evidence_directive_snapshots
    USING (ibex_core.rls_org_visible(org_id));

GRANT SELECT, INSERT, UPDATE, DELETE ON ibex_core.evidence_directive_snapshots TO ibex_app;

CREATE TABLE ibex_core.evidence_tool_audits (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL
                        REFERENCES ibex_core.organizations(id)
                        ON DELETE CASCADE,
    run_id              UUID NOT NULL,
    request_id          TEXT NOT NULL,
    trace_id            TEXT NOT NULL,
    span_id             TEXT,
    tool_name           TEXT NOT NULL,
    idempotency_key     TEXT,
    sanitized_args      JSONB NOT NULL DEFAULT '{}'::jsonb,
    status              TEXT NOT NULL DEFAULT 'ok',
    error_code          TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT evidence_tool_audits_run_org_fk
        FOREIGN KEY (run_id, org_id)
        REFERENCES ibex_core.evidence_runs (id, org_id)
        ON DELETE CASCADE
);

CREATE INDEX idx_evidence_tool_audits_request
    ON ibex_core.evidence_tool_audits (org_id, request_id);

ALTER TABLE ibex_core.evidence_tool_audits ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.evidence_tool_audits FORCE ROW LEVEL SECURITY;

CREATE POLICY evidence_tool_audits_isolation ON ibex_core.evidence_tool_audits
    USING (ibex_core.rls_org_visible(org_id));

GRANT SELECT, INSERT, UPDATE, DELETE ON ibex_core.evidence_tool_audits TO ibex_app;

-- ================================================================
-- EVIDENCE OUTBOX (transactional publication; evidence-scoped only)
-- ================================================================
CREATE TABLE ibex_core.evidence_outbox (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL
                        REFERENCES ibex_core.organizations(id)
                        ON DELETE CASCADE,
    event_id            UUID NOT NULL,
    aggregate_id        TEXT NOT NULL,
    aggregate_seq       BIGINT NOT NULL,
    schema_version      TEXT NOT NULL DEFAULT 'evidence.v1', -- NOSONAR
    event_type          TEXT NOT NULL,
    payload             JSONB NOT NULL,
    payload_digest      TEXT NOT NULL,
    delivery_status     TEXT NOT NULL DEFAULT 'pending' -- NOSONAR
                        CHECK (delivery_status IN (
                            'pending', 'in_flight', 'delivered', 'failed', 'poison' -- NOSONAR
                        )),
    attempts            INTEGER NOT NULL DEFAULT 0,
    available_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    claimed_at          TIMESTAMPTZ,
    last_error          TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    delivered_at        TIMESTAMPTZ,
    UNIQUE (org_id, event_id),
    UNIQUE (org_id, aggregate_id, aggregate_seq)
);

CREATE INDEX idx_evidence_outbox_pending
    ON ibex_core.evidence_outbox (available_at, created_at)
    WHERE delivery_status IN ('pending', 'failed');

CREATE INDEX idx_evidence_outbox_org_agg
    ON ibex_core.evidence_outbox (org_id, aggregate_id, aggregate_seq);

ALTER TABLE ibex_core.evidence_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.evidence_outbox FORCE ROW LEVEL SECURITY;

CREATE POLICY evidence_outbox_isolation ON ibex_core.evidence_outbox
    USING (ibex_core.rls_org_visible(org_id));

GRANT SELECT, INSERT, UPDATE, DELETE ON ibex_core.evidence_outbox TO ibex_app;
