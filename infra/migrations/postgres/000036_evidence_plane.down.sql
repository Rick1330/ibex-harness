DROP POLICY IF EXISTS evidence_outbox_isolation ON ibex_core.evidence_outbox;
DROP TABLE IF EXISTS ibex_core.evidence_outbox;

DROP POLICY IF EXISTS evidence_tool_audits_isolation ON ibex_core.evidence_tool_audits;
DROP TABLE IF EXISTS ibex_core.evidence_tool_audits;

DROP POLICY IF EXISTS evidence_directive_snapshots_isolation ON ibex_core.evidence_directive_snapshots;
DROP TABLE IF EXISTS ibex_core.evidence_directive_snapshots;

DROP POLICY IF EXISTS evidence_score_candidates_isolation ON ibex_core.evidence_score_candidates;
DROP TABLE IF EXISTS ibex_core.evidence_score_candidates;

DROP POLICY IF EXISTS evidence_assembly_metrics_isolation ON ibex_core.evidence_assembly_metrics;
DROP TABLE IF EXISTS ibex_core.evidence_assembly_metrics;

DROP POLICY IF EXISTS evidence_events_isolation ON ibex_core.evidence_events;
DROP TABLE IF EXISTS ibex_core.evidence_events;

DROP POLICY IF EXISTS evidence_spans_isolation ON ibex_core.evidence_spans;
DROP TABLE IF EXISTS ibex_core.evidence_spans;

DROP POLICY IF EXISTS evidence_runs_isolation ON ibex_core.evidence_runs;
DROP TABLE IF EXISTS ibex_core.evidence_runs;

DROP POLICY IF EXISTS session_events_isolation ON ibex_core.session_events;
DROP TABLE IF EXISTS ibex_core.session_events;

DROP FUNCTION IF EXISTS ibex_core.rls_evidence_visible(UUID);

REVOKE ibex_service FROM ibex_app;
DROP ROLE IF EXISTS ibex_service;
