package session

import (
	"errors"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/asyncpool"
	httptrace "github.com/Rick1330/ibex-harness/services/proxy/internal/http/trace"
	"github.com/google/uuid"
)

func TestUnit_CaptureTraceSnapshot_Guards(t *testing.T) {
	t.Parallel()

	meta := testSnapshotMeta()
	tests := []struct {
		name string
		meta SnapshotMeta
	}{
		{name: "empty meta", meta: SnapshotMeta{}},
		{name: "missing request_id", meta: SnapshotMeta{OrgID: meta.OrgID, AgentID: meta.AgentID}},
		{name: "nil org", meta: SnapshotMeta{RequestID: "r", AgentID: meta.AgentID}},
		{name: "nil agent", meta: SnapshotMeta{RequestID: "r", OrgID: meta.OrgID}},
	}
	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			_, ok := CaptureTraceSnapshot(CaptureTraceArgs{Meta: tc.meta})
			if ok {
				t.Fatal("expected guard rejection")
			}
		})
	}
}

func TestUnit_CaptureTraceSnapshot_Fields(t *testing.T) {
	t.Parallel()

	sid := uuid.New()
	meta := testSnapshotMeta()
	meta.SessionID = &sid
	in := CheckpointInput{
		Model: "gpt-4o", Provider: "openai", IsStreaming: false,
		Usage:   &provider.Usage{InputTokens: 1, OutputTokens: 2},
		Latency: 250 * time.Millisecond,
	}
	outcome := httptrace.RequestOutcome{
		StatusCode: 502, IsComplete: false, ErrorCode: "PROVIDER_UNAVAILABLE",
		StreamRequested: true,
	}

	snap, ok := CaptureTraceSnapshot(CaptureTraceArgs{Meta: meta, In: in, Outcome: outcome})
	if !ok {
		t.Fatal("expected snap ok")
	}
	if snap.RequestID != meta.RequestID {
		t.Fatalf("request_id=%q", snap.RequestID)
	}
	if snap.SessionID == nil || *snap.SessionID != sid {
		t.Fatal("session id")
	}
	if !snap.Streaming {
		t.Fatal("stream requested should set streaming")
	}
	if snap.Outcome.StatusCode != 502 {
		t.Fatalf("status=%d", snap.Outcome.StatusCode)
	}
	if snap.Timings.AuthMs != meta.AuthMs {
		t.Fatalf("auth_ms=%d", snap.Timings.AuthMs)
	}
	if snap.Timings.ProviderTTFB != in.Latency {
		t.Fatalf("ttfb=%v", snap.Timings.ProviderTTFB)
	}
	if snap.Timings.RequestedAt.IsZero() {
		t.Fatal("requested_at")
	}
}

func TestUnit_CaptureTraceSnapshot_DefaultStatus(t *testing.T) {
	t.Parallel()
	snap, ok := CaptureTraceSnapshot(CaptureTraceArgs{
		Meta:    testSnapshotMeta(),
		In:      CheckpointInput{Model: "m", Provider: "openai"},
		Outcome: httptrace.RequestOutcome{StatusCode: 0, IsComplete: true},
	})
	if !ok {
		t.Fatal("snap")
	}
	if snap.Outcome.StatusCode != 200 {
		t.Fatalf("status=%d want 200", snap.Outcome.StatusCode)
	}
}

func TestUnit_EmitTrace(t *testing.T) {
	t.Parallel()

	snap := httptrace.AssembleInput{
		RequestID: "r", OrgID: uuid.New(), AgentID: uuid.New(),
		Timings: httptrace.RequestTimings{CompletedAt: time.Now().UTC()},
		Outcome: httptrace.RequestOutcome{StatusCode: 200, IsComplete: true},
	}
	tests := []struct {
		name      string
		writer    httptrace.TraceWriter
		log       *logger.Logger
		wantWrite int32
	}{
		{name: "nil writer noop", writer: nil, log: logger.Discard("t"), wantWrite: 0},
		{name: "success", writer: &recordingTraceWriter{}, log: logger.Discard("t"), wantWrite: 1},
		{name: "write error nil logger", writer: &recordingTraceWriter{err: errors.New("ch down")}, log: nil, wantWrite: 1},
	}
	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			var tw *recordingTraceWriter
			if r, ok := tc.writer.(*recordingTraceWriter); ok {
				tw = r
			}
			EmitTrace(tc.writer, tc.log, snap)
			if tw != nil && tw.writeCount() != tc.wantWrite {
				t.Fatalf("writes=%d want %d", tw.writeCount(), tc.wantWrite)
			}
		})
	}
}

func TestUnit_EnqueuePostResponse(t *testing.T) {
	t.Parallel()

	store := newMemSessionStore()
	tw := &recordingTraceWriter{}
	meta := testSnapshotMeta()
	rs := Resolved{
		SessionID: uuid.New(), ExternalID: "ext-1",
		OrgID: meta.OrgID, AgentID: meta.AgentID, TurnIndex: 0,
	}
	in := testCheckpointInput()
	snap, _ := CaptureTraceSnapshot(CaptureTraceArgs{
		Meta: meta, In: in,
		Outcome: httptrace.RequestOutcome{StatusCode: 200, IsComplete: true},
	})

	t.Run("noop when disabled", func(t *testing.T) {
		t.Parallel()
		EnqueuePostResponse(PostResponseJob{})
	})

	t.Run("sync checkpoint and trace", func(t *testing.T) {
		t.Parallel()
		EnqueuePostResponse(PostResponseJob{
			Deps: LifecycleDeps{Store: store}, In: in, Snap: snap, SnapOK: true,
			DoCheckpoint: true, DoTrace: true, TraceWriter: tw, Log: logger.Discard("t"),
			ExternalID: rs.ExternalID,
			Params:     BuildCheckpointParams(rs, in, meta.RequestID),
		})
		if store.appendCount() != 1 {
			t.Fatalf("appends=%d", store.appendCount())
		}
		if tw.writeCount() != 1 {
			t.Fatalf("writes=%d", tw.writeCount())
		}
	})

	t.Run("pool async", func(t *testing.T) {
		t.Parallel()
		pool, err := asyncpool.New(1, 4, nil)
		if err != nil {
			t.Fatal(err)
		}
		t.Cleanup(func() { _ = pool.Shutdown(t.Context()) })
		s := newMemSessionStore()
		EnqueuePostResponse(PostResponseJob{
			Deps: LifecycleDeps{Store: s, Pool: pool}, DoCheckpoint: true,
			Params: BuildCheckpointParams(rs, in, meta.RequestID), ExternalID: rs.ExternalID,
		})
		s.waitAppends(t, 1)
	})
}

func TestUnit_PreparePostResponse(t *testing.T) {
	t.Parallel()

	meta := testSnapshotMeta()
	rs := Resolved{SessionID: uuid.New(), ExternalID: "ext", OrgID: meta.OrgID, AgentID: meta.AgentID}
	in := testCheckpointInput()
	outcome := httptrace.RequestOutcome{StatusCode: 200, IsComplete: true}

	t.Run("checkpoint and trace", func(t *testing.T) {
		t.Parallel()
		job := PreparePostResponse(PreparePostResponseInput{
			Deps:   LifecycleDeps{Store: newMemSessionStore()},
			Writer: &recordingTraceWriter{}, Log: logger.Discard("t"),
			Resolved: rs, Meta: meta, In: in, Outcome: outcome,
		})
		if !job.DoCheckpoint {
			t.Fatal("expected checkpoint")
		}
		if !job.DoTrace {
			t.Fatal("expected trace")
		}
		if job.Params.SessionID != rs.SessionID {
			t.Fatalf("session=%s", job.Params.SessionID)
		}
	})

	t.Run("sticky only skips checkpoint", func(t *testing.T) {
		t.Parallel()
		sticky := Resolved{ExternalID: "sticky-only"}
		job := PreparePostResponse(PreparePostResponseInput{
			Deps: LifecycleDeps{Store: newMemSessionStore()},
			Log:  logger.Discard("t"), Resolved: sticky, Meta: meta, In: in, Outcome: outcome,
		})
		if job.DoCheckpoint {
			t.Fatal("sticky-only must not checkpoint")
		}
	})

	t.Run("failure skips checkpoint keeps trace", func(t *testing.T) {
		t.Parallel()
		failOutcome := httptrace.RequestOutcome{
			StatusCode: 502, IsComplete: false, StreamRequested: true,
		}
		job := PreparePostResponse(PreparePostResponseInput{
			Deps:   LifecycleDeps{Store: newMemSessionStore()},
			Writer: &recordingTraceWriter{}, Log: logger.Discard("t"),
			Resolved: rs, Meta: meta, In: in, Outcome: failOutcome,
		})
		if job.DoCheckpoint {
			t.Fatal("failure must not checkpoint")
		}
		if !job.DoTrace {
			t.Fatal("expected failure trace")
		}
		if !job.Snap.Streaming {
			t.Fatal("stream flag preserved in snap")
		}
	})
}
