package http

import (
	"context"
	"net/http"
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

type recordingTraceWriter struct {
	mu      sync.Mutex
	records []ibexch.TraceRecord
	err     error
	writes  atomic.Int32
}

func (r *recordingTraceWriter) Write(rec ibexch.TraceRecord) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.records = append(r.records, rec)
	r.writes.Add(1)
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
