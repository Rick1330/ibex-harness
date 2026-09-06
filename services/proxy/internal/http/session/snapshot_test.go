package session

import (
	"bytes"
	"context"
	"errors"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/asyncpool"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/extractionbuffer"
	httptrace "github.com/Rick1330/ibex-harness/services/proxy/internal/http/trace"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
	"github.com/alicebob/miniredis/v2"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/require"
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
	require.True(t, ok, "expected snap ok")
	require.Equal(t, meta.RequestID, snap.RequestID, "request_id")
	require.NotNil(t, snap.SessionID, "session id")
	require.Equal(t, sid, *snap.SessionID, "session id")
	require.True(t, snap.Streaming, "stream requested should set streaming")
	require.Equal(t, outcome.StatusCode, snap.Outcome.StatusCode, "status")
	require.False(t, snap.Outcome.IsComplete, "is_complete")
	require.Equal(t, meta.AuthMs, snap.Timings.AuthMs, "auth_ms")
	require.Equal(t, in.Latency, snap.Timings.ProviderTTFB, "ttfb")
	require.False(t, snap.Timings.RequestedAt.IsZero(), "requested_at")
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
		logBuf    *bytes.Buffer
	}{
		{name: "nil writer noop", writer: nil, log: logger.Discard("t"), wantWrite: 0},
		{name: "success", writer: &recordingTraceWriter{}, log: logger.Discard("t"), wantWrite: 1},
		{name: "write error nil logger", writer: &recordingTraceWriter{err: errors.New("ch down")}, log: nil, wantWrite: 1},
		{name: "write error with logger", writer: &recordingTraceWriter{err: errors.New("ch down")}, log: testBufferedLogger(t), wantWrite: 1},
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

func testBufferedLogger(t *testing.T) *logger.Logger {
	t.Helper()
	log, err := logger.New(logger.Config{Service: "proxy", Writer: &bytes.Buffer{}})
	if err != nil {
		t.Fatal(err)
	}
	return log
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

func TestUnit_PreparePostResponse_CheckpointAndTrace(t *testing.T) {
	t.Parallel()
	job := preparePostResponseJob(t, prepareJobArgs{
		outcome: httptrace.RequestOutcome{StatusCode: 200, IsComplete: true},
		writer:  true,
	})
	assertPrepareFlags(t, job, prepareFlags{checkpoint: true, trace: true})
	if job.Params.SessionID == uuid.Nil {
		t.Fatal("expected session id")
	}
}

func TestUnit_PreparePostResponse_StickySkipsCheckpoint(t *testing.T) {
	t.Parallel()
	job := preparePostResponseJob(t, prepareJobArgs{
		outcome: httptrace.RequestOutcome{StatusCode: 200, IsComplete: true},
		sticky:  true,
	})
	if job.DoCheckpoint {
		t.Fatal("sticky-only must not checkpoint")
	}
	if job.DoBuffer {
		t.Fatal("without TurnBuffer, sticky must not buffer")
	}
}

func TestUnit_PreparePostResponse_StickyBuffersWithoutCheckpoint(t *testing.T) {
	t.Parallel()
	meta := testSnapshotMeta()
	buf := newTestTurnBuffer(t)
	rs := Resolved{ExternalID: "sticky-only"}
	job := PreparePostResponse(PreparePostResponseInput{
		Deps:     LifecycleDeps{Store: newMemSessionStore(), TurnBuffer: buf, Log: logger.Discard("t")},
		Log:      logger.Discard("t"),
		Resolved: rs, Meta: meta, In: bufferCheckpointInput("sticky-user", "sticky-reply"),
		Outcome: httptrace.RequestOutcome{StatusCode: 200, IsComplete: true},
	})
	assertStickyBufferJob(t, job, meta, rs.ExternalID)
	EnqueuePostResponse(job)
	assertFlushedTurns(t, buf, job.BufferKey, 2)
}

func TestUnit_PreparePostResponse_FailureKeepsTrace(t *testing.T) {
	t.Parallel()
	job := preparePostResponseJob(t, prepareJobArgs{
		outcome: httptrace.RequestOutcome{StatusCode: 502, IsComplete: false, StreamRequested: true},
		writer:  true,
	})
	assertPrepareFlags(t, job, prepareFlags{checkpoint: false, trace: true, streaming: true})
}

func TestUnit_PreparePostResponse_TurnBufferFlushes(t *testing.T) {
	t.Parallel()
	meta := testSnapshotMeta()
	rs := Resolved{SessionID: uuid.New(), ExternalID: "ext", OrgID: meta.OrgID, AgentID: meta.AgentID}
	buf := newTestTurnBuffer(t)
	job := PreparePostResponse(PreparePostResponseInput{
		Deps:   LifecycleDeps{Store: newMemSessionStore(), TurnBuffer: buf, Log: logger.Discard("t")},
		Writer: &recordingTraceWriter{}, Log: logger.Discard("t"),
		Resolved: rs, Meta: meta, In: bufferCheckpointInput("hello-buf", "reply"),
		Outcome: httptrace.RequestOutcome{StatusCode: 200, IsComplete: true},
	})
	if !job.DoBuffer {
		t.Fatal("expected DoBuffer")
	}
	if len(job.BufferTurns) != 2 {
		t.Fatalf("buffer turns=%d", len(job.BufferTurns))
	}
	EnqueuePostResponse(job)
	assertFlushedTurns(t, buf, job.BufferKey, 2)
}

func newTestTurnBuffer(t *testing.T) *extractionbuffer.Buffer {
	t.Helper()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	buf, err := extractionbuffer.New(client, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	return buf
}

func bufferCheckpointInput(user, reply string) CheckpointInput {
	return CheckpointInput{
		Messages:       []llm.Message{{Role: "user", Content: user}, {Role: "assistant", Content: "ignored"}},
		CompletionText: reply, Model: "m", Provider: "p",
	}
}

func assertStickyBufferJob(t *testing.T, job PostResponseJob, meta SnapshotMeta, ext string) {
	t.Helper()
	if job.DoCheckpoint {
		t.Fatal("sticky-only must not checkpoint")
	}
	if !job.DoBuffer {
		t.Fatal("sticky successful turn must buffer with Meta org/agent")
	}
	assertBufferKeyFromMeta(t, job.BufferKey, meta, ext)
}

func assertBufferKeyFromMeta(t *testing.T, key extractionbuffer.LookupKey, meta SnapshotMeta, ext string) {
	t.Helper()
	if key.OrgID != meta.OrgID {
		t.Fatalf("BufferKey.OrgID=%s want %s", key.OrgID, meta.OrgID)
	}
	if key.AgentID != meta.AgentID {
		t.Fatalf("BufferKey.AgentID=%s want %s", key.AgentID, meta.AgentID)
	}
	if key.ExternalID != ext {
		t.Fatalf("BufferKey.ExternalID=%q want %q", key.ExternalID, ext)
	}
}

func assertFlushedTurns(t *testing.T, buf *extractionbuffer.Buffer, key extractionbuffer.LookupKey, want int) {
	t.Helper()
	snap, err := buf.Peek(context.Background(), key)
	if err != nil {
		t.Fatal(err)
	}
	if len(snap.Turns) != want {
		t.Fatalf("flushed turns=%d want %d", len(snap.Turns), want)
	}
}

type prepareJobArgs struct {
	outcome httptrace.RequestOutcome
	writer  bool
	sticky  bool
}

type prepareFlags struct {
	checkpoint bool
	trace      bool
	streaming  bool
}

func preparePostResponseJob(t *testing.T, a prepareJobArgs) PostResponseJob {
	t.Helper()
	meta := testSnapshotMeta()
	rs := Resolved{SessionID: uuid.New(), ExternalID: "ext", OrgID: meta.OrgID, AgentID: meta.AgentID}
	if a.sticky {
		rs = Resolved{ExternalID: "sticky-only"}
	}
	in := PreparePostResponseInput{
		Deps: LifecycleDeps{Store: newMemSessionStore()},
		Log:  logger.Discard("t"), Resolved: rs, Meta: meta, In: testCheckpointInput(), Outcome: a.outcome,
	}
	if a.writer {
		in.Writer = &recordingTraceWriter{}
	}
	return PreparePostResponse(in)
}

func assertPrepareFlags(t *testing.T, job PostResponseJob, want prepareFlags) {
	t.Helper()
	if job.DoCheckpoint != want.checkpoint {
		t.Fatalf("DoCheckpoint=%v want %v", job.DoCheckpoint, want.checkpoint)
	}
	if job.DoTrace != want.trace {
		t.Fatalf("DoTrace=%v want %v", job.DoTrace, want.trace)
	}
	if want.streaming && !job.Snap.Streaming {
		t.Fatal("stream flag preserved in snap")
	}
}
