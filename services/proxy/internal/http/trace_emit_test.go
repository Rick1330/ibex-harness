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
	if rec.RequestID != "req-1" || rec.OrgID != org || rec.AgentID != agent {
		t.Fatalf("ids: %+v", rec)
	}
	if rec.SessionID == nil || *rec.SessionID != sid {
		t.Fatal("session")
	}
	if rec.CheckpointID != nil {
		t.Fatal("checkpoint_id must be nil")
	}
	if rec.InputTokens != 10 || rec.OutputTokens != 20 || rec.TotalTokens != 30 {
		t.Fatalf("tokens: %+v", rec)
	}
	if rec.AuthLatencyMs != 5 || rec.DirectiveLatencyMs != 7 || rec.ProviderTTFBMs != 40 {
		t.Fatalf("latencies: %+v", rec)
	}
	if rec.TotalLatencyMs != 150 {
		t.Fatalf("total_ms=%d", rec.TotalLatencyMs)
	}
	assertNoContentFields(t, rec)
}

func TestUnit_AssembleTrace_NilUsageZeros(t *testing.T) {
	t.Parallel()
	rec := assembleTrace(traceAssembleInput{
		RequestID: "r", OrgID: uuid.New(), AgentID: uuid.New(),
		Timings: requestTimings{CompletedAt: time.Now().UTC()},
		Outcome: requestOutcome{StatusCode: 502, IsComplete: false, ErrorCode: "PROVIDER_UNAVAILABLE"},
	})
	if rec.TotalTokens != 0 || rec.IsComplete || rec.ErrorCode == "" {
		t.Fatalf("%+v", rec)
	}
}

func assertNoContentFields(t *testing.T, rec ibexch.TraceRecord) {
	t.Helper()
	forbidden := map[string]struct{}{
		"Prompt": {}, "Completion": {}, "Content": {}, "Messages": {},
	}
	rt := reflect.TypeOf(rec)
	for i := 0; i < rt.NumField(); i++ {
		if _, ok := forbidden[rt.Field(i).Name]; ok {
			t.Fatalf("forbidden field %s", rt.Field(i).Name)
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

func TestUnit_EnqueuePostResponse_EmitsTrace(t *testing.T) {
	t.Parallel()
	tw := &recordingTraceWriter{}
	pool, err := asyncpool.New(2, 8, nil)
	if err != nil {
		t.Fatal(err)
	}
	cleanupPool(t, pool)
	h := chatCompletionHandler{
		log: logger.Discard("proxy"), checkpointPool: pool, traceWriter: tw,
	}
	ctx := authedTraceContext(t)
	h.enqueuePostResponse(ctx, checkpointInput{
		Model: "gpt-4o", Provider: "openai", Latency: 12 * time.Millisecond,
		IsStreaming: false, IsComplete: true,
	}, requestOutcome{StatusCode: 200, IsComplete: true})
	tw.waitWrites(t, 1)
	rec, ok := tw.last()
	if !ok || rec.Model != "gpt-4o" || !rec.IsComplete {
		t.Fatalf("%+v", rec)
	}
}

func TestUnit_EnqueuePostResponse_WriteErrorDoesNotPanic(t *testing.T) {
	t.Parallel()
	tw := &recordingTraceWriter{err: errors.New("ch down")}
	h := chatCompletionHandler{
		log: logger.Discard("proxy"), traceWriter: tw,
	}
	h.enqueuePostResponse(authedTraceContext(t), checkpointInput{
		Model: "m", Provider: "openai", IsComplete: true,
	}, requestOutcome{StatusCode: 200, IsComplete: true})
	if tw.writes.Load() != 1 {
		t.Fatalf("writes=%d", tw.writes.Load())
	}
}

func TestUnit_EnqueuePostResponse_NilWriterNoop(t *testing.T) {
	t.Parallel()
	h := chatCompletionHandler{log: logger.Discard("proxy")}
	h.enqueuePostResponse(authedTraceContext(t), checkpointInput{
		Model: "m", Provider: "openai", IsComplete: true,
	}, requestOutcome{StatusCode: 200, IsComplete: true})
}

func TestUnit_EnqueuePostResponse_NoTenantSkipsTrace(t *testing.T) {
	t.Parallel()
	tw := &recordingTraceWriter{}
	h := chatCompletionHandler{log: logger.Discard("proxy"), traceWriter: tw}
	h.enqueuePostResponse(context.Background(), checkpointInput{
		Model: "m", Provider: "openai", IsComplete: true,
	}, requestOutcome{StatusCode: 200, IsComplete: true})
	if tw.writes.Load() != 0 {
		t.Fatal("expected skip without tenant")
	}
}

func TestUnit_ChatCompletions_EmitsTraceOnSuccess(t *testing.T) {
	t.Parallel()
	tw := &recordingTraceWriter{}
	pool, err := asyncpool.New(2, 8, nil)
	if err != nil {
		t.Fatal(err)
	}
	cleanupPool(t, pool)
	handler := chatRouterWithTrace(t, tw, pool)
	rec := postChat(t, handler, chatRequestOpts{
		body: `{"model":"gpt-4o","messages":[{"role":"user","content":"hi"}]}`,
		auth: true, agentID: testChatAgentID,
	})
	if rec.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
	tw.waitWrites(t, 1)
	got, ok := tw.last()
	if !ok || got.Provider != "openai" || got.Model != "gpt-4o" {
		t.Fatalf("%+v", got)
	}
}

func TestUnit_ChatCompletions_EmitsTraceOnProviderFailure(t *testing.T) {
	t.Parallel()
	tw := &recordingTraceWriter{}
	pool, err := asyncpool.New(2, 8, nil)
	if err != nil {
		t.Fatal(err)
	}
	cleanupPool(t, pool)
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
	if !ok || got.IsComplete || got.ErrorCode == "" {
		t.Fatalf("%+v", got)
	}
}

func TestUnit_ChatCompletions_WriteErrorKeepsHTTPOK(t *testing.T) {
	t.Parallel()
	tw := &recordingTraceWriter{err: errors.New("flush fail")}
	pool, err := asyncpool.New(2, 8, nil)
	if err != nil {
		t.Fatal(err)
	}
	cleanupPool(t, pool)
	handler := chatRouterWithTrace(t, tw, pool)
	rec := postChat(t, handler, chatRequestOpts{
		body: `{"model":"gpt-4o","messages":[{"role":"user","content":"hi"}]}`,
		auth: true, agentID: testChatAgentID,
	})
	if rec.Code != http.StatusOK {
		t.Fatalf("status=%d", rec.Code)
	}
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
	if AuthLatencyMsFromContext(ctx) != 9 || DirectiveLatencyMsFromContext(ctx) != 11 {
		t.Fatal("latency context")
	}
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
