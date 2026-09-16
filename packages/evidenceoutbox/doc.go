// Package evidenceoutbox implements the 4.P.2 evidence-scoped transactional outbox
// and durable evidence-plane writers (runs, spans, assembly metrics, scores,
// directive snapshots, tool audits, session_events linkage).
//
// Scope is intentionally narrow: do not use this package for model-policy
// invalidation or org-deletion cascades.
//
// Outbox claim/mark/recover SECURITY DEFINER helpers are executable only by
// role ibex_evidence_relay (not ibex_app). Wire the future relay daemon to that
// role; PersistRun remains on the normal app connection with org GUC RLS.
package evidenceoutbox

// SchemaVersion is the envelope version for evidence records and outbox payloads.
const SchemaVersion = "evidence.v1"

// ScoreSchemaInterim labels the current context-assembly scoring mix (0.85/0.15).
const ScoreSchemaInterim = "interim_v1"

// Delivery statuses for evidence_outbox.delivery_status.
const (
	StatusPending   = "pending"
	StatusInFlight  = "in_flight"
	StatusDelivered = "delivered"
	StatusFailed    = "failed"
	StatusPoison    = "poison"
)

// Known event types published through the outbox.
const (
	EventTypeRunCommitted    = "evidence.run.committed"
	EventTypeSpanCommitted   = "evidence.span.committed"
	EventTypeAssemblyMetrics = "evidence.assembly_metrics"
	EventTypeScoreCandidates = "evidence.score_candidates"
	EventTypeDirectiveSnap   = "evidence.directive_snapshot"
	EventTypeToolAudit       = "evidence.tool_audit"
	EventTypeSessionEvent    = "evidence.session_event"
)
