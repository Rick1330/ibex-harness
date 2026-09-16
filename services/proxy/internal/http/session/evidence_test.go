package session

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/evidenceoutbox"
	"github.com/Rick1330/ibex-harness/packages/logger"
	httptrace "github.com/Rick1330/ibex-harness/services/proxy/internal/http/trace"
	"github.com/google/uuid"
)

type fakeEvidenceStore struct {
	calls int
	last  evidenceoutbox.RunInput
	err   error
}

func (f *fakeEvidenceStore) PersistRun(_ context.Context, in evidenceoutbox.RunInput) (evidenceoutbox.PersistResult, error) {
	f.calls++
	f.last = in
	if f.err != nil {
		return evidenceoutbox.PersistResult{}, f.err
	}
	return evidenceoutbox.PersistResult{RunID: uuid.New(), AggregateID: in.TraceID}, nil
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
