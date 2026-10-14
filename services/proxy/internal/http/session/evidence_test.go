package session

import (
	"context"
	"errors"
	"net/http"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/evidenceoutbox"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/provider"
	pkgssession "github.com/Rick1330/ibex-harness/packages/session"
	httptrace "github.com/Rick1330/ibex-harness/services/proxy/internal/http/trace"
	"github.com/google/uuid"
)

type fakeEvidenceStore struct {
	calls     int
	last      evidenceoutbox.RunInput
	err       error
	result    evidenceoutbox.PersistResult
	useResult bool
	proof     *evidenceoutbox.ReconciliationProof
	proofErr  error
}

type fakeEvidenceFenceStore struct {
	fence pkgssession.EvidenceFence
}

func (f fakeEvidenceFenceStore) LookupEvidenceFence(_ context.Context, _, _ uuid.UUID) (pkgssession.EvidenceFence, error) {
	return f.fence, nil
}

func (f *fakeEvidenceStore) PersistRun(_ context.Context, in evidenceoutbox.RunInput) (evidenceoutbox.PersistResult, error) {
	f.calls++
	f.last = in
	if f.err != nil {
		return evidenceoutbox.PersistResult{}, f.err
	}
	if f.useResult {
		return f.result, nil
	}
	return evidenceoutbox.PersistResult{RunID: uuid.New(), OutboxIDs: []uuid.UUID{uuid.New()}, AggregateID: in.TraceID}, nil
}

func (f *fakeEvidenceStore) ReconcileRun(_ context.Context, _ evidenceoutbox.RunInput) (evidenceoutbox.ReconciliationProof, error) {
	if f.proofErr != nil {
		return evidenceoutbox.ReconciliationProof{}, f.proofErr
	}
	if f.proof == nil {
		return evidenceoutbox.ReconciliationProof{}, evidenceoutbox.ErrReconciliationNotProven
	}
	return *f.proof, nil
}

func TestUnit_BuildEvidenceRun_RequiresTraceAndRequest(t *testing.T) {
	t.Parallel()
	org := uuid.New()
	agent := uuid.New()
	in := BuildEvidenceRun(httptrace.AssembleInput{
		RequestID: "req-1", OrgID: org, AgentID: agent,
	}, SnapshotMeta{}, EvidenceExtras{})
	if len(in.Spans) != 0 {
		t.Fatalf("expected no spans without trace_id, got %+v", in.Spans)
	}
}

func TestUnit_BuildEvidenceRun_NestedSpans(t *testing.T) {
	t.Parallel()
	in := buildNestedEvidenceRun(t)
	assertNestedEvidenceRun(t, in)
}

func TestUnit_BuildEvidenceRun_PropagatesProducerProof(t *testing.T) {
	t.Parallel()
	producer := &evidenceoutbox.ProducerMetadata{
		RedactionClass:        evidenceoutbox.RedactionClassMetadata,
		RedactionProofVersion: "redaction/v1",
		ResourceType:          "evidence_run", ResourceID: "run-1", ResourceVersion: 3,
		Source: "proxy.session",
	}
	in := BuildEvidenceRun(httptrace.AssembleInput{
		RequestID: "req-1", OrgID: uuid.New(), AgentID: uuid.New(),
	}, SnapshotMeta{}, EvidenceExtras{Producer: producer})
	if in.Producer != producer || in.RedactionClass != producer.RedactionClass {
		t.Fatalf("producer metadata was not propagated: %+v", in)
	}
	if in.TombstoneFence == nil || in.TombstoneFence.ResourceVersion != producer.ResourceVersion {
		t.Fatalf("producer fence was not propagated: %+v", in.TombstoneFence)
	}
}

func buildNestedEvidenceRun(t *testing.T) evidenceoutbox.RunInput {
	t.Helper()
	org := uuid.New()
	agent := uuid.New()
	ck := uuid.New()
	vid := uuid.New()
	now := time.Now().UTC()
	return BuildEvidenceRun(httptrace.AssembleInput{
		RequestID: "req-1", OrgID: org, AgentID: agent,
		TraceID: "aabbccddeeff00112233445566778899", RootSpanID: "aabbccddeeff0011",
		CheckpointID: &ck, DirectiveVersionID: &vid,
		ContextAssemblyMs: 12, Completeness: "complete",
		Timings: httptrace.RequestTimings{RequestedAt: now, CompletedAt: now},
		Outcome: httptrace.RequestOutcome{StatusCode: 200, IsComplete: true},
	}, SnapshotMeta{ContextAssemblyMs: 12}, EvidenceExtras{
		Metrics:        &evidenceoutbox.AssemblyMetrics{TotalMs: 12},
		AssembleSpanID: "1122334455667788",
	})
}

func assertNestedEvidenceRun(t *testing.T, in evidenceoutbox.RunInput) {
	t.Helper()
	assertJoinKeys(t, in)
	assertAssembleChildSpan(t, in)
	assertNestedStatus(t, in)
}

func assertJoinKeys(t *testing.T, in evidenceoutbox.RunInput) {
	t.Helper()
	if in.TraceID == "" || in.CheckpointID == nil {
		t.Fatalf("missing join keys: %+v", in)
	}
	if len(in.Spans) != 2 {
		t.Fatalf("spans=%d want 2", len(in.Spans))
	}
	if in.MetricsSpanID != "1122334455667788" {
		t.Fatalf("metrics span=%q want AssembleSpanID", in.MetricsSpanID)
	}
}

func assertNestedStatus(t *testing.T, in evidenceoutbox.RunInput) {
	t.Helper()
	if in.Status != "ok" {
		t.Fatalf("status=%q", in.Status)
	}
	if in.Completeness != "complete" {
		t.Fatalf("completeness=%q", in.Completeness)
	}
	if in.Directive == nil || in.Directive.DirectiveVersionID == nil {
		t.Fatal("expected directive snapshot")
	}
}

func TestUnit_BuildEvidenceRun_RejectsInvalidW3CIDs(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name           string
		traceID        string
		rootSpanID     string
		assembleSpanID string
		wantTrace      string
		wantRoot       string
		wantMetrics    string
		wantSpans      int
	}{
		{
			name:    "bad_root",
			traceID: "aabbccddeeff00112233445566778899", rootSpanID: "not-hex",
			assembleSpanID: "1122334455667788",
			wantTrace:      "aabbccddeeff00112233445566778899",
			wantMetrics:    "1122334455667788", wantSpans: 0,
		},
		{
			name:    "bad_trace",
			traceID: "not-a-w3c-trace", rootSpanID: "aabbccddeeff0011",
			assembleSpanID: "1122334455667788",
			wantRoot:       "aabbccddeeff0011", wantMetrics: "1122334455667788", wantSpans: 0,
		},
		{
			name:    "bad_assemble",
			traceID: "aabbccddeeff00112233445566778899", rootSpanID: "aabbccddeeff0011",
			assembleSpanID: "bad-span",
			wantTrace:      "aabbccddeeff00112233445566778899", wantRoot: "aabbccddeeff0011",
			wantSpans: 1,
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			in := BuildEvidenceRun(httptrace.AssembleInput{
				RequestID: "req-1", OrgID: uuid.New(), AgentID: uuid.New(),
				TraceID: tc.traceID, RootSpanID: tc.rootSpanID,
				Outcome: httptrace.RequestOutcome{StatusCode: 200, IsComplete: true},
			}, SnapshotMeta{}, EvidenceExtras{AssembleSpanID: tc.assembleSpanID})
			if in.TraceID != tc.wantTrace {
				t.Fatalf("trace=%q want %q", in.TraceID, tc.wantTrace)
			}
			if in.RootSpanID != tc.wantRoot {
				t.Fatalf("root=%q want %q", in.RootSpanID, tc.wantRoot)
			}
			if in.MetricsSpanID != tc.wantMetrics {
				t.Fatalf("metrics=%q want %q", in.MetricsSpanID, tc.wantMetrics)
			}
			if len(in.Spans) != tc.wantSpans {
				t.Fatalf("spans=%d want %d", len(in.Spans), tc.wantSpans)
			}
		})
	}
}

func assertAssembleChildSpan(t *testing.T, in evidenceoutbox.RunInput) {
	t.Helper()
	if in.Spans[1].SpanID != "1122334455667788" {
		t.Fatalf("assemble span=%q", in.Spans[1].SpanID)
	}
	if in.Spans[1].ParentSpanID != "aabbccddeeff0011" {
		t.Fatalf("parent=%q", in.Spans[1].ParentSpanID)
	}
}

func TestUnit_BuildEvidenceRun_ErrorOutcome(t *testing.T) {
	t.Parallel()
	org := uuid.New()
	agent := uuid.New()
	in := BuildEvidenceRun(httptrace.AssembleInput{
		RequestID: "req-err", OrgID: org, AgentID: agent,
		TraceID: "aabbccddeeff00112233445566778899", RootSpanID: "aabbccddeeff0011",
		Outcome: httptrace.RequestOutcome{
			StatusCode: 502, IsComplete: false, ErrorCode: "PROVIDER_UNAVAILABLE",
		},
	}, SnapshotMeta{}, EvidenceExtras{AssembleSpanID: "1122334455667788"})
	if in.Status != "error" {
		t.Fatalf("status=%q want error", in.Status)
	}
	if in.Completeness != "partial" {
		t.Fatalf("completeness=%q", in.Completeness)
	}
	if in.Spans[0].Status != "error" || in.Spans[1].Status != "error" {
		t.Fatalf("span statuses=%q/%q", in.Spans[0].Status, in.Spans[1].Status)
	}
	if in.ErrorCode != "PROVIDER_UNAVAILABLE" {
		t.Fatalf("error_code=%q", in.ErrorCode)
	}
}

func TestUnit_BuildCertifiedEvidenceRun_ErrorOutcomeRemainsMetadata(t *testing.T) {
	t.Parallel()
	orgID, agentID, sessionID := uuid.New(), uuid.New(), uuid.New()
	store := fakeEvidenceFenceStore{fence: pkgssession.EvidenceFence{
		ResourceType: "session", ResourceID: sessionID, ResourceVersion: 4,
	}}
	in, err := BuildCertifiedEvidenceRun(context.Background(), store, httptrace.AssembleInput{
		RequestID: "req-certified-error", OrgID: orgID, AgentID: agentID, SessionID: &sessionID,
		TraceID: "aabbccddeeff00112233445566778899", RootSpanID: "aabbccddeeff0011",
		Usage:   &provider.Usage{InputTokens: 120, OutputTokens: 45},
		Outcome: httptrace.RequestOutcome{StatusCode: 502, IsComplete: false, ErrorCode: "PROVIDER_UNAVAILABLE"},
	}, SnapshotMeta{}, EvidenceExtras{AssembleSpanID: "1122334455667788"})
	if err != nil {
		t.Fatalf("BuildCertifiedEvidenceRun() error = %v", err)
	}
	if in.RedactionClass != evidenceoutbox.RedactionClassMetadata || in.Status != "error" {
		t.Fatalf("classification/status = %q/%q", in.RedactionClass, in.Status)
	}
	if in.ErrorCode != "" || in.Spans[0].ErrorCode != "" || in.Spans[1].ErrorCode != "" {
		t.Fatalf("free-form error code survived: run=%q spans=%q/%q", in.ErrorCode, in.Spans[0].ErrorCode, in.Spans[1].ErrorCode)
	}
	if in.TokenUsage == nil || in.TokenUsage.TotalTokens != 165 {
		t.Fatalf("total token fallback = %+v", in.TokenUsage)
	}
}

func TestUnit_EffectiveEvidence_TypedNil(t *testing.T) {
	t.Parallel()
	var typedNil *fakeEvidenceStore
	if EffectiveEvidence(typedNil) != nil {
		t.Fatal("typed-nil must become true nil")
	}
	if EffectiveEvidence(nil) != nil {
		t.Fatal("nil interface")
	}
	real := &fakeEvidenceStore{}
	if EffectiveEvidence(real) == nil {
		t.Fatal("non-nil store must pass through")
	}
}

func TestUnit_PersistEvidence_FailOpen(t *testing.T) {
	t.Parallel()
	store := &fakeEvidenceStore{err: errors.New("db down")}
	PersistEvidence(store, logger.Discard("t"), evidenceoutbox.RunInput{
		OrgID: uuid.New(), RequestID: "r", TraceID: "t",
	})
	if store.calls != 1 {
		t.Fatalf("calls=%d", store.calls)
	}
	PersistEvidence(nil, logger.Discard("t"), evidenceoutbox.RunInput{})
	var typedNil *fakeEvidenceStore
	PersistEvidence(typedNil, logger.Discard("t"), evidenceoutbox.RunInput{
		OrgID: uuid.New(), RequestID: "r", TraceID: "t",
	})
}

func TestUnit_PersistEvidenceWithAck(t *testing.T) {
	t.Parallel()
	in := evidenceoutbox.RunInput{OrgID: uuid.New(), RequestID: "r", TraceID: "t"}
	good := &fakeEvidenceStore{}
	outcome := PersistEvidenceWithAck(context.Background(), good, in)
	if outcome.Status != EvidenceAckDurable {
		t.Fatalf("durable status=%q", outcome.Status)
	}
	if outcome.Err != nil {
		t.Fatalf("durable err=%v", outcome.Err)
	}
	failed := &fakeEvidenceStore{err: errors.New("db down")}
	outcome = PersistEvidenceWithAck(context.Background(), failed, in)
	if outcome.Status != EvidenceAckUnavailable {
		t.Fatalf("failed status=%q", outcome.Status)
	}
	if outcome.Err == nil {
		t.Fatal("uncertified outcome has no error")
	}
	unknown := &fakeEvidenceStore{useResult: true, result: evidenceoutbox.PersistResult{}}
	outcome = PersistEvidenceWithAck(context.Background(), unknown, in)
	if outcome.Status != EvidenceAckUnknown {
		t.Fatalf("unknown status=%q", outcome.Status)
	}
	if outcome.Err == nil {
		t.Fatal("unknown outcome has no error")
	}
	if outcome.Err.Error() != "evidence commit outcome is unknown" {
		t.Fatalf("unknown error=%q", outcome.Err)
	}
}

func TestUnit_BuildEvidenceRun_DeployImageDigestFromEnv(t *testing.T) {
	t.Setenv("IBEX_DEPLOY_IMAGE_DIGEST", "  sha256:abcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcd  ")
	in := BuildEvidenceRun(httptrace.AssembleInput{
		RequestID: "req-1", OrgID: uuid.New(), AgentID: uuid.New(),
		TraceID: "aabbccddeeff00112233445566778899", RootSpanID: "aabbccddeeff0011",
		Outcome: httptrace.RequestOutcome{StatusCode: 200, IsComplete: true},
	}, SnapshotMeta{}, EvidenceExtras{})
	want := "sha256:abcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcd"
	if in.DeployImageDigest != want {
		t.Fatalf("digest=%q want %q", in.DeployImageDigest, want)
	}
}

func TestUnit_BuildEvidenceRun_DeployImageDigestUnset(t *testing.T) {
	t.Setenv("IBEX_DEPLOY_IMAGE_DIGEST", "")
	in := BuildEvidenceRun(httptrace.AssembleInput{
		RequestID: "req-1", OrgID: uuid.New(), AgentID: uuid.New(),
	}, SnapshotMeta{}, EvidenceExtras{})
	if in.DeployImageDigest != "" {
		t.Fatalf("digest=%q want empty", in.DeployImageDigest)
	}
}

func TestUnit_PersistEvidenceForProfile_GoldenOutcomes(t *testing.T) {
	t.Parallel()
	agentID, sessionID := uuid.New(), uuid.New()
	in := evidenceoutbox.RunInput{OrgID: uuid.New(), AgentID: &agentID, SessionID: &sessionID, RequestID: "r", TraceID: "t"}
	proofRunID, proofOutboxID := uuid.New(), uuid.New()
	proof := &evidenceoutbox.ReconciliationProof{
		OrgID: in.OrgID, AgentID: &agentID, SessionID: &sessionID,
		RequestID: in.RequestID, TraceID: in.TraceID, RunID: proofRunID,
		OutboxIDs: []uuid.UUID{proofOutboxID}, RetryableOutboxIDs: []uuid.UUID{proofOutboxID},
	}
	cases := []struct {
		name       string
		store      *fakeEvidenceStore
		profile    EvidenceAckProfile
		wantStatus EvidenceAckStatus
		wantHTTP   int
	}{
		{name: "durable", store: &fakeEvidenceStore{}, profile: EvidenceAckProfile{Required: true}, wantStatus: EvidenceAckDurable, wantHTTP: http.StatusOK},
		{name: "failed-required", store: &fakeEvidenceStore{err: errors.New("db down")}, profile: EvidenceAckProfile{Required: true}, wantStatus: EvidenceAckUnavailable, wantHTTP: http.StatusServiceUnavailable},
		{name: "failed-degraded-without-proof", store: &fakeEvidenceStore{err: errors.New("db down")}, profile: EvidenceAckProfile{Required: true, AllowUncertified: true}, wantStatus: EvidenceAckUnavailable, wantHTTP: http.StatusServiceUnavailable},
		{name: "degraded-with-durable-retry-proof", store: &fakeEvidenceStore{err: errors.New("db down"), proof: proof}, profile: EvidenceAckProfile{Required: true, AllowUncertified: true}, wantStatus: EvidenceAckUncertified, wantHTTP: http.StatusAccepted},
		{name: "reconciled-replay", store: &fakeEvidenceStore{err: errors.New("ack lost"), proof: &evidenceoutbox.ReconciliationProof{
			OrgID: in.OrgID, AgentID: &agentID, SessionID: &sessionID, RequestID: in.RequestID, TraceID: in.TraceID,
			RunID: proofRunID, OutboxIDs: []uuid.UUID{proofOutboxID},
		}}, profile: EvidenceAckProfile{Required: true}, wantStatus: EvidenceAckReplay, wantHTTP: http.StatusOK},
		{name: "unknown", store: &fakeEvidenceStore{useResult: true, result: evidenceoutbox.PersistResult{}}, profile: EvidenceAckProfile{Required: true}, wantStatus: EvidenceAckUnknown, wantHTTP: http.StatusServiceUnavailable},
		{name: "replay", store: &fakeEvidenceStore{useResult: true, result: evidenceoutbox.PersistResult{RunID: uuid.New(), OutboxIDs: []uuid.UUID{uuid.New()}, Replayed: true}}, profile: EvidenceAckProfile{Required: true}, wantStatus: EvidenceAckReplay, wantHTTP: http.StatusOK},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			out := PersistEvidenceForProfile(context.Background(), tc.store, in, tc.profile)
			if out.Status != tc.wantStatus {
				t.Fatalf("status=%q want %q err=%v", out.Status, tc.wantStatus, out.Err)
			}
			if tc.name == "replay" && out.Err != nil {
				t.Fatalf("reconciled replay retained error: %v", out.Err)
			}
			got, _ := EvidenceAckHTTP(out)
			if got != tc.wantHTTP {
				t.Fatalf("http=%d want %d", got, tc.wantHTTP)
			}
		})
	}
}
