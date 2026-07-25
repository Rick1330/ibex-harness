package http

import (
	"context"
	"errors"
	"net/http"
	"reflect"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	ibexch "github.com/Rick1330/ibex-harness/packages/clickhouse"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/permissions"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/asyncpool"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
	"github.com/google/uuid"
)

func TestUnit_AssembleTrace_MapsFields(t *testing.T) {
	t.Parallel()
	org := uuid.MustParse("11111111-1111-1111-1111-111111111111")
	agent := uuid.MustParse("22222222-2222-2222-2222-222222222222")
	sid := uuid.MustParse("33333333-3333-3333-3333-333333333333")
	start := time.Date(2026, 7, 25, 12, 0, 0, 0, time.UTC)
	end := start.Add(150 * time.Millisecond)

	rec := assembleTrace(traceAssembleInput{
		RequestID: "req-1", OrgID: org, AgentID: agent, SessionID: &sid,
		Model: "gpt-4o", Provider: "openai", Streaming: true,
		Usage: &provider.Usage{InputTokens: 10, OutputTokens: 20, TotalTokens: 30},
		Timings: requestTimings{
			AuthMs: 5, DirectiveMs: 7, ProviderTTFB: 40 * time.Millisecond,
			RequestedAt: start, CompletedAt: end,
		},
		Outcome: requestOutcome{StatusCode: 200, IsComplete: true},
	})
	assertAssembleIDs(t, rec, org, agent, sid)
	assertAssembleTokens(t, rec)
	assertAssembleLatencies(t, rec)
	assertNoContentFields(t, rec)
}

func assertAssembleIDs(t *testing.T, rec ibexch.TraceRecord, org, agent, sid uuid.UUID) {
	t.Helper()
	if rec.RequestID != "req-1" {
		t.Fatalf("request_id=%s", rec.RequestID)
	}
	if rec.OrgID != org {
		t.Fatalf("org=%s", rec.OrgID)
	}
	if rec.AgentID != agent {
		t.Fatalf("agent=%s", rec.AgentID)
	}
	if rec.SessionID == nil {
		t.Fatal("session nil")
	}
	if *rec.SessionID != sid {
		t.Fatalf("session=%s", *rec.SessionID)
	}
	if rec.CheckpointID != nil {
		t.Fatal("checkpoint_id must be nil")
	}
}

func assertAssembleTokens(t *testing.T, rec ibexch.TraceRecord) {
	t.Helper()
	if rec.InputTokens != 10 {
		t.Fatalf("input=%d", rec.InputTokens)
	}
	if rec.OutputTokens != 20 {
		t.Fatalf("output=%d", rec.OutputTokens)
	}
	if rec.TotalTokens != 30 {
		t.Fatalf("total=%d", rec.TotalTokens)
	}
}

func assertAssembleLatencies(t *testing.T, rec ibexch.TraceRecord) {
	t.Helper()
	if rec.AuthLatencyMs != 5 {
		t.Fatalf("auth=%d", rec.AuthLatencyMs)
	}
	if rec.DirectiveLatencyMs != 7 {
		t.Fatalf("directive=%d", rec.DirectiveLatencyMs)
	}
	if rec.ProviderTTFBMs != 40 {
		t.Fatalf("ttfb=%d", rec.ProviderTTFBMs)
	}
	if rec.TotalLatencyMs != 150 {
		t.Fatalf("total_ms=%d", rec.TotalLatencyMs)
	}
}

func TestUnit_AssembleTrace_NilUsageZeros(t *testing.T) {
	t.Parallel()
	rec := assembleTrace(traceAssembleInput{
		RequestID: "r", OrgID: uuid.New(), AgentID: uuid.New(),
		Timings: requestTimings{CompletedAt: time.Now().UTC()},
		Outcome: requestOutcome{StatusCode: 502, IsComplete: false, ErrorCode: "PROVIDER_UNAVAILABLE"},
	})
	if rec.TotalTokens != 0 {
		t.Fatalf("tokens=%d", rec.TotalTokens)
	}
	if rec.IsComplete {
		t.Fatal("expected incomplete")
	}
	if rec.ErrorCode == "" {
		t.Fatal("expected error_code")
	}
}

func TestUnit_AssembleTrace_DefaultsAndUsageSum(t *testing.T) {
	t.Parallel()
	rec := assembleTrace(traceAssembleInput{
		RequestID: "r", OrgID: uuid.New(), AgentID: uuid.New(),
		Usage:   &provider.Usage{InputTokens: 3, OutputTokens: 4},
		Timings: requestTimings{}, // zero times → filled
		Outcome: requestOutcome{StatusCode: 0, IsComplete: true},
	})
	if rec.TotalTokens != 7 {
		t.Fatalf("sum total=%d", rec.TotalTokens)
	}
	if rec.RequestedAt.IsZero() {
		t.Fatal("requested_at")
	}
	if rec.CompletedAt.IsZero() {
		t.Fatal("completed_at")
	}
}

func TestUnit_TraceHelpers_Clamp(t *testing.T) {
	t.Parallel()
	if durationToUint32(-time.Second) != 0 {
		t.Fatal("neg duration")
	}
	overU32 := (time.Duration(^uint32(0)) + 1) * time.Millisecond
	if durationToUint32(overU32) != ^uint32(0) {
		t.Fatal("duration overflow")
	}
	if intToUint32(-1) != 0 {
		t.Fatal("neg int")
	}
	if intToUint32(int(^uint32(0))+1) != ^uint32(0) {
		t.Fatal("int overflow")
	}
	if clampUint16Ms(-time.Millisecond) != 0 {
		t.Fatal("neg clamp")
	}
	overU16 := (time.Duration(^uint16(0)) + 1) * time.Millisecond
	if clampUint16Ms(overU16) != ^uint16(0) {
		t.Fatal("clamp overflow")
	}
}

func assertNoContentFields(t *testing.T, rec ibexch.TraceRecord) {
	t.Helper()
	forbidden := map[string]struct{}{
		"Prompt": {}, "Completion": {}, "Content": {}, "Messages": {},
	}
	rt := reflect.TypeOf(rec)
	for i := 0; i < rt.NumField(); i++ {
		name := rt.Field(i).Name
		if _, ok := forbidden[name]; ok {
			t.Fatalf("forbidden field %s", name)
		}
	}
}

type recordingTraceWriter struct {
	mu      sync.Mutex
	records []ibexch.TraceRecord
	err     error
	writes  atomic.Int32
}

func (r *recordingTraceWriter) Write(rec ibexch.TraceRecord) error {
	r.writes.Add(1)
	r.mu.Lock()
	defer r.mu.Unlock()
	r.records = append(r.records, rec)
	return r.err
}

func (r *recordingTraceWriter) last() (ibexch.TraceRecord, bool) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if len(r.records) == 0 {
		return ibexch.TraceRecord{}, false
	}
	return r.records[len(r.records)-1], true
}

func (r *recordingTraceWriter) waitWrites(t *testing.T, n int32) {
	t.Helper()
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		if r.writes.Load() >= n {
			return
		}
		time.Sleep(5 * time.Millisecond)
	}
	t.Fatalf("writes=%d want >=%d", r.writes.Load(), n)
}

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

func TestUnit_EnqueuePostResponse_NilWriterNoop(t *testing.T) {
	t.Parallel()
	h := chatCompletionHandler{log: logger.Discard("proxy")}
	h.enqueuePostResponse(authedTraceContext(t), checkpointInput{
		Model: "m", Provider: "openai", IsComplete: true,
	}, requestOutcome{StatusCode: 200, IsComplete: true})
}

func TestUnit_EnqueuePostResponse_FailureSkipsCheckpoint(t *testing.T) {
	t.Parallel()
	store := newMemSessionStore()
	tw := &recordingTraceWriter{}
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
		SessionID: sid, OrgID: org, AgentID: agent, ExternalID: "ext-1", TurnIndex: 0,
	})

	h := chatCompletionHandler{
		log: logger.Discard("proxy"), sessionStore: store,
		checkpointPool: pool, traceWriter: tw,
	}
	h.enqueuePostResponse(ctx, checkpointInput{
		Model: "gpt-4o", Provider: "openai", IsComplete: false,
	}, requestOutcome{StatusCode: 502, IsComplete: false, ErrorCode: "PROVIDER_UNAVAILABLE"})
	tw.waitWrites(t, 1)
	time.Sleep(50 * time.Millisecond)
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

func TestUnit_EmitTrace_NilLogger(t *testing.T) {
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
}

func TestUnit_ChatCompletions_EmitsTraceOnSuccess(t *testing.T) {
	t.Parallel()
	tw := &recordingTraceWriter{}
	pool := mustPool(t)
	handler := chatRouterWithTrace(t, tw, pool)
	rec := postChat(t, handler, chatRequestOpts{
		body: `{"model":"gpt-4o","messages":[{"role":"user","content":"hi"}]}`,
		auth: true, agentID: testChatAgentID,
	})
	assertStatusOK(t, rec.Code)
	tw.waitWrites(t, 1)
	got, ok := tw.last()
	if !ok {
		t.Fatal("no write")
	}
	if got.Provider != "openai" {
		t.Fatalf("provider=%s", got.Provider)
	}
	if got.Model != "gpt-4o" {
		t.Fatalf("model=%s", got.Model)
	}
}

func TestUnit_ChatCompletions_EmitsTraceOnProviderFailure(t *testing.T) {
	t.Parallel()
	tw := &recordingTraceWriter{}
	pool := mustPool(t)
	reg, err := provider.NewRegistry(stubLLMProvider{
		name: "openai", models: []string{"gpt-4o"},
		err: &provider.ProviderError{ProviderName: "openai", StatusCode: http.StatusBadGateway},
	})
	if err != nil {
		t.Fatal(err)
	}
	handler := NewRouter(RouterDeps{
		Config: chatTestConfig(), Logger: logger.Discard("proxy"),
		Metrics: metrics.NewProxy("test"), Tracer: telemetry.NoopTracer("proxy"),
		Validator: &chatMockValidator{res: &auth.ValidateResult{
			OrgID: testChatOrgID, Permissions: permissions.ProxyChatCompletion,
		}},
		AgentVerifier: passAgentVerifier{}, Limiter: ratelimit.Noop(),
		CheckpointPool: pool, TraceWriter: tw,
		Health: testHealthServer(), ProviderRegistry: reg,
	})
	rec := postChat(t, handler, chatRequestOpts{
		body: `{"model":"gpt-4o","messages":[{"role":"user","content":"hi"}]}`,
		auth: true, agentID: testChatAgentID,
	})
	if rec.Code == http.StatusOK {
		t.Fatal("expected provider failure status")
	}
	tw.waitWrites(t, 1)
	got, ok := tw.last()
	if !ok {
		t.Fatal("no write")
	}
	if got.IsComplete {
		t.Fatal("expected incomplete")
	}
	if got.ErrorCode == "" {
		t.Fatal("expected error_code")
	}
}

func TestUnit_ChatCompletions_WriteErrorKeepsHTTPOK(t *testing.T) {
	t.Parallel()
	tw := &recordingTraceWriter{err: errors.New("flush fail")}
	handler := chatRouterWithTrace(t, tw, mustPool(t))
	rec := postChat(t, handler, chatRequestOpts{
		body: `{"model":"gpt-4o","messages":[{"role":"user","content":"hi"}]}`,
		auth: true, agentID: testChatAgentID,
	})
	assertStatusOK(t, rec.Code)
	tw.waitWrites(t, 1)
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

func TestUnit_StageLatencyContext(t *testing.T) {
	t.Parallel()
	ctx := WithAuthLatencyMs(context.Background(), 9)
	ctx = WithDirectiveLatencyMs(ctx, 11)
	if AuthLatencyMsFromContext(ctx) != 9 {
		t.Fatal("auth")
	}
	if DirectiveLatencyMsFromContext(ctx) != 11 {
		t.Fatal("directive")
	}
}

func assertStatusOK(t *testing.T, code int) {
	t.Helper()
	if code != http.StatusOK {
		t.Fatalf("status=%d", code)
	}
}

func mustPool(t *testing.T) *asyncpool.Pool {
	t.Helper()
	pool, err := asyncpool.New(2, 8, nil)
	if err != nil {
		t.Fatal(err)
	}
	cleanupPool(t, pool)
	return pool
}

func authedTraceContext(t *testing.T) context.Context {
	t.Helper()
	org := uuid.MustParse(testChatOrgID)
	agent := uuid.MustParse(testChatAgentID)
	ctx := WithRequestID(context.Background(), "req-trace-1")
	ctx = WithRequestStart(ctx, time.Now().UTC().Add(-100*time.Millisecond))
	ctx = auth.WithContext(ctx, &auth.ValidateResult{
		OrgID: org.String(), Permissions: permissions.ProxyChatCompletion,
	})
	ctx = WithAgent(ctx, auth.AgentRecord{ID: agent, OrgID: org})
	ctx = WithAuthLatencyMs(ctx, 3)
	ctx = WithDirectiveLatencyMs(ctx, 4)
	return ctx
}

func chatRouterWithTrace(t *testing.T, tw TraceWriter, pool *asyncpool.Pool) http.Handler {
	t.Helper()
	reg, err := provider.NewRegistry(stubLLMProvider{
		name: "openai", models: []string{"gpt-4o"},
		body: `{"choices":[{"message":{"content":"hello"}}]}`,
	})
	if err != nil {
		t.Fatal(err)
	}
	return NewRouter(RouterDeps{
		Config: chatTestConfig(), Logger: logger.Discard("proxy"),
		Metrics: metrics.NewProxy("test"), Tracer: telemetry.NoopTracer("proxy"),
		Validator: &chatMockValidator{res: &auth.ValidateResult{
			OrgID: testChatOrgID, Permissions: permissions.ProxyChatCompletion,
		}},
		AgentVerifier: passAgentVerifier{}, Limiter: ratelimit.Noop(),
		CheckpointPool: pool, TraceWriter: tw,
		Health: testHealthServer(), ProviderRegistry: reg,
	})
}
