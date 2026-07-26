package http

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/asyncpool"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
	"github.com/google/uuid"
)

func TestUnit_EnqueuePostResponse_Cases(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name      string
		ctx       func(*testing.T) context.Context
		tw        *recordingTraceWriter
		wantWrite int32
	}{
		{
			name:      "emits",
			ctx:       authedTraceContext,
			tw:        &recordingTraceWriter{},
			wantWrite: 1,
		},
		{
			name:      "write_error",
			ctx:       authedTraceContext,
			tw:        &recordingTraceWriter{err: errors.New("ch down")},
			wantWrite: 1,
		},
		{
			name:      "no_tenant",
			ctx:       func(*testing.T) context.Context { return context.Background() },
			tw:        &recordingTraceWriter{},
			wantWrite: 0,
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			h := chatCompletionHandler{log: logger.Discard("proxy"), traceWriter: tc.tw}
			h.enqueuePostResponse(tc.ctx(t), checkpointInput{
				Model: "gpt-4o", Provider: "openai", IsComplete: true,
			}, requestOutcome{StatusCode: 200, IsComplete: true})
			if tc.tw.writes.Load() != tc.wantWrite {
				t.Fatalf("writes=%d want %d", tc.tw.writes.Load(), tc.wantWrite)
			}
		})
	}
}

func TestUnit_EffectiveTraceWriter_TypedNil(t *testing.T) {
	t.Parallel()
	var ptr *recordingTraceWriter
	var iface TraceWriter = ptr
	if iface == nil {
		t.Fatal("precondition: boxed typed-nil must be non-nil interface")
	}
	if effectiveTraceWriter(iface) != nil {
		t.Fatal("expected true nil after normalize")
	}
	if effectiveTraceWriter(nil) != nil {
		t.Fatal("nil stays nil")
	}
	live := &recordingTraceWriter{}
	if effectiveTraceWriter(live) == nil {
		t.Fatal("non-nil writer preserved")
	}
}

func TestUnit_EnqueuePostResponse_TypedNilWriterNoop(t *testing.T) {
	t.Parallel()
	var ptr *recordingTraceWriter
	h := chatCompletionHandler{
		log: logger.Discard("proxy"), traceWriter: ptr, // typed nil boxed
	}
	h.enqueuePostResponse(authedTraceContext(t), checkpointInput{
		Model: "m", Provider: "openai", IsComplete: true,
	}, requestOutcome{StatusCode: 200, IsComplete: true})
}

func TestUnit_EnqueuePostResponse_FailureSkipsCheckpoint(t *testing.T) {
	t.Parallel()
	store := newMemSessionStore()
	tw := &recordingTraceWriter{}
	org := uuid.MustParse(testChatOrgID)
	agent := uuid.MustParse(testChatAgentID)
	sid := uuid.New()
	ctx := authedTraceContext(t)
	ctx = withResolvedSession(ctx, resolvedSession{
		SessionID: sid, OrgID: org, AgentID: agent, ExternalID: "ext-1", TurnIndex: 0,
	})

	// Nil pool runs Submit work synchronously so appendCalls is deterministic.
	h := chatCompletionHandler{
		log: logger.Discard("proxy"), sessionStore: store, traceWriter: tw,
	}
	h.enqueuePostResponse(ctx, checkpointInput{
		Model: "gpt-4o", Provider: "openai", IsComplete: false,
	}, requestOutcome{
		StatusCode: 502, IsComplete: false, ErrorCode: "PROVIDER_UNAVAILABLE",
		StreamRequested: true,
	})
	if tw.writes.Load() != 1 {
		t.Fatalf("writes=%d", tw.writes.Load())
	}
	got, ok := tw.last()
	if !ok {
		t.Fatal("no record")
	}
	if !got.IsStreaming {
		t.Fatal("failure trace should preserve stream request flag")
	}
	store.mu.Lock()
	n := store.appendCalls
	store.mu.Unlock()
	if n != 0 {
		t.Fatalf("checkpoint appends=%d want 0 on failure", n)
	}
}

func TestUnit_EnqueuePostResponse_IncompleteStreamStillCheckpoints(t *testing.T) {
	t.Parallel()
	store := newMemSessionStore()
	pool, err := asyncpool.New(2, 8, nil)
	if err != nil {
		t.Fatal(err)
	}
	cleanupPool(t, pool)

	org := uuid.MustParse(testChatOrgID)
	agent := uuid.MustParse(testChatAgentID)
	sid := uuid.New()
	ctx := authedTraceContext(t)
	ctx = withResolvedSession(ctx, resolvedSession{
		SessionID: sid, OrgID: org, AgentID: agent, ExternalID: "ext-2", TurnIndex: 0,
	})
	h := chatCompletionHandler{
		log: logger.Discard("proxy"), sessionStore: store, checkpointPool: pool,
	}
	h.enqueuePostResponse(ctx, checkpointInput{
		Model: "gpt-4o", Provider: "openai", IsStreaming: true, IsComplete: false,
		Messages: []llm.Message{{Role: "user", Content: "hi"}},
	}, requestOutcome{StatusCode: 200, IsComplete: false, ErrorCode: "STREAM_INCOMPLETE"})
	store.waitAppends(t, 1)
}

func TestUnit_CaptureTraceSnapshot_Guards(t *testing.T) {
	t.Parallel()
	h := chatCompletionHandler{}
	_, ok := h.captureTraceSnapshot(context.Background(), checkpointInput{}, requestOutcome{})
	if ok {
		t.Fatal("expected no tenant")
	}
	ctx := WithAgent(context.Background(), auth.AgentRecord{
		ID: uuid.MustParse(testChatAgentID), OrgID: uuid.MustParse(testChatOrgID),
	})
	ctx = auth.WithContext(ctx, &auth.ValidateResult{OrgID: testChatOrgID})
	_, ok = h.captureTraceSnapshot(ctx, checkpointInput{}, requestOutcome{IsComplete: true})
	if ok {
		t.Fatal("expected empty request_id skip")
	}
}

func TestUnit_CaptureTraceSnapshot_DefaultStatus(t *testing.T) {
	t.Parallel()
	h := chatCompletionHandler{}
	snap, ok := h.captureTraceSnapshot(authedTraceContext(t), checkpointInput{
		Model: "m", Provider: "openai",
	}, requestOutcome{StatusCode: 0, IsComplete: true})
	if !ok {
		t.Fatal("snap")
	}
	if snap.Outcome.StatusCode != 200 {
		t.Fatalf("status=%d", snap.Outcome.StatusCode)
	}
}

func TestUnit_CaptureTraceSnapshot_DurableSession(t *testing.T) {
	t.Parallel()
	sid := uuid.New()
	ctx := authedTraceContext(t)
	ctx = withResolvedSession(ctx, resolvedSession{
		SessionID: sid, OrgID: uuid.MustParse(testChatOrgID),
		AgentID: uuid.MustParse(testChatAgentID), ExternalID: "ext",
	})
	h := chatCompletionHandler{}
	snap, ok := h.captureTraceSnapshot(ctx, checkpointInput{Model: "m"}, requestOutcome{StatusCode: 200, IsComplete: true})
	if !ok {
		t.Fatal("snap")
	}
	if snap.SessionID == nil {
		t.Fatal("session id")
	}
	if *snap.SessionID != sid {
		t.Fatalf("got %s", *snap.SessionID)
	}
}

func TestUnit_EnqueuePostResponse_EmitTrace_NilLogger(t *testing.T) {
	t.Parallel()
	tw := &recordingTraceWriter{err: errors.New("x")}
	h := chatCompletionHandler{traceWriter: tw}
	h.emitTrace(traceAssembleInput{
		RequestID: "r", OrgID: uuid.New(), AgentID: uuid.New(),
		Timings: requestTimings{CompletedAt: time.Now().UTC()},
		Outcome: requestOutcome{StatusCode: 200, IsComplete: true},
	})
	if tw.writes.Load() != 1 {
		t.Fatal("write")
	}
}

func TestUnit_FailureTraceIdentity(t *testing.T) {
	t.Parallel()
	model, prov := failureTraceIdentity(providerFailureParams{
		parsed: &llm.ChatCompletionRequest{Model: "gpt-4o"},
		err:    &provider.ProviderError{ProviderName: "openai"},
	})
	if model != "gpt-4o" {
		t.Fatalf("model=%s", model)
	}
	if prov != "openai" {
		t.Fatalf("provider=%s", prov)
	}
	_, prov2 := failureTraceIdentity(providerFailureParams{providerName: "explicit"})
	if prov2 != "explicit" {
		t.Fatalf("explicit=%s", prov2)
	}
	if !failureStreamRequested(providerFailureParams{
		parsed: &llm.ChatCompletionRequest{Stream: true},
	}) {
		t.Fatal("stream requested")
	}
}

func TestUnit_EnqueuePostResponse_Concurrent(t *testing.T) {
	t.Parallel()
	tw := &recordingTraceWriter{}
	pool, err := asyncpool.New(4, 64, nil)
	if err != nil {
		t.Fatal(err)
	}
	cleanupPool(t, pool)
	h := chatCompletionHandler{
		log: logger.Discard("proxy"), checkpointPool: pool, traceWriter: tw,
	}
	ctx := authedTraceContext(t)
	var wg sync.WaitGroup
	for i := 0; i < 20; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			h.enqueuePostResponse(ctx, checkpointInput{
				Model: "gpt-4o", Provider: "openai", IsComplete: true,
			}, requestOutcome{StatusCode: 200, IsComplete: true})
		}()
	}
	wg.Wait()
	tw.waitWrites(t, 20)
}
