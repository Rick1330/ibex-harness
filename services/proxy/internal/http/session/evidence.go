package session

import (
	"context"
	"time"

	"github.com/Rick1330/ibex-harness/packages/evidenceoutbox"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/reqid"
	httptrace "github.com/Rick1330/ibex-harness/services/proxy/internal/http/trace"
)

// EvidencePersister is the optional 4.P.2 durable evidence write path.
// Implementations must be fail-open at the call site: Persist errors never
// surface to the chat client.
type EvidencePersister interface {
	PersistRun(ctx context.Context, in evidenceoutbox.RunInput) (evidenceoutbox.PersistResult, error)
}

// PersistEvidence writes nested evidence + outbox rows when a persister is configured.
// Failures are logged and discarded (same policy as EmitTrace / ClickHouse).
func PersistEvidence(
	p EvidencePersister,
	log *logger.Logger,
	in evidenceoutbox.RunInput,
) {
	if p == nil {
		return
	}
	ctx, cancel := context.WithTimeout(context.Background(), CheckpointTaskTimeout)
	defer cancel()
	if in.RequestID != "" {
		ctx = reqid.WithRequestID(ctx, in.RequestID)
	}
	_, err := p.PersistRun(ctx, in)
	if err == nil || log == nil {
		return
	}
	log.WarnCtx(ctx, "evidence persist failed",
		"error", err.Error(),
		"request_id", in.RequestID,
		"org_id", in.OrgID.String(),
	)
}

// EvidenceExtras carries assemble-time contracts into the durable evidence write.
type EvidenceExtras struct {
	Metrics        *evidenceoutbox.AssemblyMetrics
	Candidates     []evidenceoutbox.ScoreCandidate
	AssembleSpanID string
}

// BuildEvidenceRun maps a completed post-response snapshot into PersistRun input.
func BuildEvidenceRun(snap httptrace.AssembleInput, meta SnapshotMeta, extras EvidenceExtras) evidenceoutbox.RunInput {
	in := baseEvidenceRun(snap, meta, extras)
	if in.TraceID == "" || in.RequestID == "" {
		return in
	}
	if in.RootSpanID == "" {
		in.RootSpanID = "unknown"
	}
	in.Spans = evidenceSpans(in, extras)
	in.Directive = evidenceDirective(snap, meta)
	return in
}

func baseEvidenceRun(snap httptrace.AssembleInput, meta SnapshotMeta, extras EvidenceExtras) evidenceoutbox.RunInput {
	agent := snap.AgentID
	started := snap.Timings.RequestedAt
	ended := snap.Timings.CompletedAt
	if started.IsZero() {
		started = time.Now().UTC()
	}
	if ended.IsZero() {
		ended = started
	}
	return evidenceoutbox.RunInput{
		OrgID:        snap.OrgID,
		AgentID:      &agent,
		SessionID:    snap.SessionID,
		RequestID:    snap.RequestID,
		TraceID:      firstNonEmpty(snap.TraceID, meta.TraceID),
		RootSpanID:   firstNonEmpty(snap.RootSpanID, meta.RootSpanID),
		CheckpointID: snap.CheckpointID,
		Completeness: firstNonEmpty(snap.Completeness, "partial"),
		Status:       "ok",
		StartedAt:    started,
		EndedAt:      ended,
		Metrics:      extras.Metrics,
		Candidates:   extras.Candidates,
	}
}

func evidenceSpans(in evidenceoutbox.RunInput, extras EvidenceExtras) []evidenceoutbox.SpanInput {
	root := in.RootSpanID
	spans := []evidenceoutbox.SpanInput{
		{SpanID: root, OperationKind: "proxy.chat", Status: "ok", StartedAt: in.StartedAt, EndedAt: in.EndedAt},
	}
	assembleID := extras.AssembleSpanID
	if assembleID == "" {
		return spans
	}
	return append(spans, evidenceoutbox.SpanInput{
		SpanID:        assembleID,
		ParentSpanID:  root,
		OperationKind: "context.assemble",
		Status:        "ok",
		StartedAt:     in.StartedAt,
		EndedAt:       in.EndedAt,
	})
}

func evidenceDirective(snap httptrace.AssembleInput, meta SnapshotMeta) *evidenceoutbox.DirectiveSnapshot {
	vid := meta.DirectiveVersionID
	if vid == nil {
		vid = snap.DirectiveVersionID
	}
	if vid == nil {
		return nil
	}
	return &evidenceoutbox.DirectiveSnapshot{DirectiveVersionID: vid}
}

func firstNonEmpty(values ...string) string {
	for _, v := range values {
		if v != "" {
			return v
		}
	}
	return ""
}
