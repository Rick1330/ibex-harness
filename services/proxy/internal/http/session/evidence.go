package session

import (
	"context"
	"os"
	"reflect"
	"strings"
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

// EffectiveEvidence returns a true-nil interface when p is nil or a typed-nil
// pointer/interface (same pattern as httptrace.EffectiveWriter).
func EffectiveEvidence(p EvidencePersister) EvidencePersister {
	if p == nil {
		return nil
	}
	v := reflect.ValueOf(p)
	switch v.Kind() {
	case reflect.Pointer, reflect.Interface, reflect.Map, reflect.Slice, reflect.Chan, reflect.Func:
		if v.IsNil() {
			return nil
		}
	}
	return p
}

// PersistEvidence writes nested evidence + outbox rows when a persister is configured.
// Failures are logged and discarded (same policy as EmitTrace / ClickHouse).
func PersistEvidence(
	p EvidencePersister,
	log *logger.Logger,
	in evidenceoutbox.RunInput,
) {
	p = EffectiveEvidence(p)
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
	in.TraceID = w3cTraceIDOrEmpty(in.TraceID)
	in.RootSpanID = w3cSpanIDOrEmpty(in.RootSpanID)
	extras.AssembleSpanID = w3cSpanIDOrEmpty(extras.AssembleSpanID)
	// Always overwrite so a raw invalid AssembleSpanID cannot linger from baseEvidenceRun.
	in.MetricsSpanID = extras.AssembleSpanID
	if in.TraceID == "" || in.RequestID == "" {
		return in
	}
	if in.RootSpanID != "" {
		in.Spans = evidenceSpans(in, extras)
	}
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
	status, completeness := evidenceStatusFromOutcome(snap)
	return evidenceoutbox.RunInput{
		OrgID:             snap.OrgID,
		AgentID:           &agent,
		SessionID:         snap.SessionID,
		RequestID:         snap.RequestID,
		TraceID:           firstNonEmpty(snap.TraceID, meta.TraceID),
		RootSpanID:        firstNonEmpty(snap.RootSpanID, meta.RootSpanID),
		CheckpointID:      snap.CheckpointID,
		Completeness:      completeness,
		Status:            status,
		ErrorCode:         snap.Outcome.ErrorCode,
		StartedAt:         started,
		EndedAt:           ended,
		Metrics:           extras.Metrics,
		Candidates:        extras.Candidates,
		DeployImageDigest: deployImageDigestFromEnv(),
	}
}

// deployImageDigestFromEnv reads the OCI digest injected by Helm/CI
// (IBEX_DEPLOY_IMAGE_DIGEST). Empty when unset (local/dev).
func deployImageDigestFromEnv() string {
	return strings.TrimSpace(os.Getenv("IBEX_DEPLOY_IMAGE_DIGEST"))
}

func evidenceStatusFromOutcome(snap httptrace.AssembleInput) (status, completeness string) {
	if outcomeIsError(snap.Outcome) {
		return "error", firstNonEmpty(snap.Completeness, "partial")
	}
	if !snap.Outcome.IsComplete {
		return "ok", firstNonEmpty(snap.Completeness, "partial")
	}
	return "ok", firstNonEmpty(snap.Completeness, "complete")
}

func outcomeIsError(outcome httptrace.RequestOutcome) bool {
	if outcome.ErrorCode != "" {
		return true
	}
	return !outcome.IsComplete && outcome.StatusCode >= 400
}

func evidenceSpans(in evidenceoutbox.RunInput, extras EvidenceExtras) []evidenceoutbox.SpanInput {
	spanStatus := "ok"
	if in.Status != "ok" {
		spanStatus = in.Status
	}
	root := in.RootSpanID
	spans := []evidenceoutbox.SpanInput{
		{
			SpanID: root, OperationKind: "proxy.chat", Status: spanStatus,
			ErrorCode: in.ErrorCode, StartedAt: in.StartedAt, EndedAt: in.EndedAt,
		},
	}
	assembleID := extras.AssembleSpanID
	if assembleID == "" {
		return spans
	}
	return append(spans, evidenceoutbox.SpanInput{
		SpanID:        assembleID,
		ParentSpanID:  root,
		OperationKind: "context.assemble",
		Status:        spanStatus,
		ErrorCode:     in.ErrorCode,
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

func w3cTraceIDOrEmpty(id string) string {
	if !isW3CHex(id, 32) || id == strings.Repeat("0", 32) {
		return ""
	}
	return strings.ToLower(id)
}

func w3cSpanIDOrEmpty(id string) string {
	if !isW3CHex(id, 16) || id == strings.Repeat("0", 16) {
		return ""
	}
	return strings.ToLower(id)
}

func isW3CHex(s string, length int) bool {
	if len(s) != length {
		return false
	}
	for i := 0; i < len(s); i++ {
		c := s[i]
		switch {
		case c >= '0' && c <= '9', c >= 'a' && c <= 'f', c >= 'A' && c <= 'F':
		default:
			return false
		}
	}
	return true
}
