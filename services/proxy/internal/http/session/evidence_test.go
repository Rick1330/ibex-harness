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
	org := uuid.New()
	agent := uuid.New()
	ck := uuid.New()
	vid := uuid.New()
	now := time.Now().UTC()
	in := BuildEvidenceRun(httptrace.AssembleInput{
		RequestID: "req-1", OrgID: org, AgentID: agent,
		TraceID: "aabbccddeeff00112233445566778899", RootSpanID: "rootspan1",
		CheckpointID: &ck, DirectiveVersionID: &vid,
		ContextAssemblyMs: 12, Completeness: "complete",
		Timings: httptrace.RequestTimings{RequestedAt: now, CompletedAt: now},
	}, SnapshotMeta{ContextAssemblyMs: 12}, EvidenceExtras{
		Metrics: &evidenceoutbox.AssemblyMetrics{TotalMs: 12},
	})
	if in.TraceID == "" || in.CheckpointID == nil {
		t.Fatalf("missing join keys: %+v", in)
	}
	if len(in.Spans) != 2 {
		t.Fatalf("spans=%d want 2", len(in.Spans))
	}
	if in.Spans[1].ParentSpanID != "rootspan1" {
		t.Fatalf("parent=%q", in.Spans[1].ParentSpanID)
	}
	if in.Directive == nil || in.Directive.DirectiveVersionID == nil {
		t.Fatal("expected directive snapshot")
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
}
