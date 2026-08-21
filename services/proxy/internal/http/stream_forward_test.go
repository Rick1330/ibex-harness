package http

import (
	"context"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"runtime"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/permissions"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/google/uuid"
)

type streamStubProvider struct {
	name      string
	models    []string
	body      string
	chunks    []string
	delay     time.Duration
	hang      bool
	failAfter int
	entered   chan struct{}
	wg        sync.WaitGroup
}

func (s *streamStubProvider) Complete(ctx context.Context, req provider.Request) (provider.Response, error) {
	if !req.Stream {
		return provider.Response{
			StatusCode: http.StatusOK,
			Body:       io.NopCloser(strings.NewReader(s.body)),
		}, nil
	}
	pr, pw := io.Pipe()
	s.wg.Add(1)
	go s.writeChunks(ctx, pw)
	return provider.Response{StatusCode: http.StatusOK, Body: pr}, nil
}

func (s *streamStubProvider) writeChunks(ctx context.Context, pw *io.PipeWriter) {
	defer s.wg.Done()
	defer func() { _ = pw.Close() }()
	if s.hang {
		s.waitHang(ctx, pw)
		return
	}
	for i, chunk := range s.chunks {
		if err := s.writeOneChunk(ctx, pw, i, chunk); err != nil {
			return
		}
	}
}

func (s *streamStubProvider) waitHang(ctx context.Context, pw *io.PipeWriter) {
	s.signalEntered()
	<-ctx.Done()
	_ = pw.CloseWithError(ctx.Err())
}

func (s *streamStubProvider) signalEntered() {
	if s.entered == nil {
		return
	}
	select {
	case <-s.entered:
	default:
		close(s.entered)
	}
}

func (s *streamStubProvider) writeOneChunk(ctx context.Context, pw *io.PipeWriter, i int, chunk string) error {
	if err := s.waitDelay(ctx, pw); err != nil {
		return err
	}
	if _, err := pw.Write([]byte(chunk)); err != nil {
		return err
	}
	if s.failAfter > 0 && i+1 >= s.failAfter {
		err := errors.New("upstream mid-stream failure")
		_ = pw.CloseWithError(err)
		return err
	}
	return nil
}

func (s *streamStubProvider) waitDelay(ctx context.Context, pw *io.PipeWriter) error {
	if s.delay <= 0 {
		return nil
	}
	select {
	case <-ctx.Done():
		_ = pw.CloseWithError(ctx.Err())
		return ctx.Err()
	case <-time.After(s.delay):
		return nil
	}
}

func (s *streamStubProvider) Name() string { return s.name }

func (s *streamStubProvider) SupportedModels() []string { return s.models }

type flushRecorder struct {
	*httptest.ResponseRecorder
	mu     sync.Mutex
	events []string
}

func newFlushRecorder() *flushRecorder {
	return &flushRecorder{ResponseRecorder: httptest.NewRecorder()}
}

func (f *flushRecorder) Flush() {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.events = append(f.events, f.Body.String())
}

func (f *flushRecorder) snapshots() []string {
	f.mu.Lock()
	defer f.mu.Unlock()
	out := make([]string, len(f.events))
	copy(out, f.events)
	return out
}

func TestUnit_Streaming_ForwardsChunksInOrder(t *testing.T) {
	t.Parallel()
	chunks := []string{
		"data: {\"choices\":[{\"delta\":{\"content\":\"A\"}}]}\n\n",
		"data: {\"choices\":[{\"delta\":{\"content\":\"B\"}}]}\n\n",
		"data: {\"choices\":[{\"delta\":{\"content\":\"C\"}}]}\n\n",
		"data: {\"choices\":[{\"delta\":{\"content\":\"D\"}}]}\n\n",
		"data: {\"choices\":[{\"delta\":{\"content\":\"E\"}}]}\n\n",
		"data: [DONE]\n\n",
	}
	stub := &streamStubProvider{
		name: "openai", models: []string{"gpt-4o"}, chunks: chunks, delay: 5 * time.Millisecond,
	}
	handler := newStreamTestHandler(t, stub)
	rec := newFlushRecorder()
	req := newStreamChatRequest(context.Background())
	start := time.Now()
	handler.ServeHTTP(rec, req)
	stub.wg.Wait()
	assertForwardedSSE(t, rec, start)
}

func newStreamTestHandler(t *testing.T, stub *streamStubProvider) http.Handler {
	t.Helper()
	return newStreamTestHandlerWithValidator(t, stub, defaultChatValidator())
}

func newStreamTestHandlerWithValidator(t *testing.T, stub *streamStubProvider, validator auth.TokenValidator) http.Handler {
	t.Helper()
	reg, err := provider.NewRegistry(provider.BuiltInCapabilityCatalog(), stub)
	if err != nil {
		t.Fatalf("NewRegistry: %v", err)
	}
	return mustNewRouter(t, RouterDeps{
		Config:           chatTestConfig(),
		Logger:           logger.Discard("proxy"),
		Metrics:          metrics.NewProxy("test"),
		Tracer:           telemetry.NoopTracer("proxy"),
		Validator:        validator,
		AgentVerifier:    passAgentVerifier{},
		Limiter:          ratelimit.Noop(),
		Health:           testHealthServer(),
		ProviderRegistry: reg,
	})
}

func newStreamChatRequest(ctx context.Context) *http.Request {
	req := httptest.NewRequestWithContext(ctx, http.MethodPost, "/v1/chat/completions", strings.NewReader(
		`{"model":"gpt-4o","messages":[{"role":"user","content":"hi"}],"stream":true}`,
	))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer test-token")
	req.Header.Set("X-IBEX-Agent-ID", testChatAgentID)
	return req
}

func assertForwardedSSE(t *testing.T, rec *flushRecorder, start time.Time) {
	t.Helper()
	if rec.Code != http.StatusOK {
		t.Fatalf("status: %d body=%s", rec.Code, rec.Body.String())
	}
	if ct := rec.Header().Get("Content-Type"); !strings.Contains(ct, "text/event-stream") {
		t.Fatalf("Content-Type: %q", ct)
	}
	if rec.Header().Get("X-Accel-Buffering") != "no" {
		t.Fatal("missing X-Accel-Buffering")
	}
	body := rec.Body.String()
	for _, want := range []string{"\"A\"", "\"B\"", "\"C\"", "\"D\"", "\"E\"", "[DONE]"} {
		if !strings.Contains(body, want) {
			t.Fatalf("body missing %q: %s", want, body)
		}
	}
	if len(rec.snapshots()) < 5 {
		t.Fatalf("expected multiple flushes, got %d", len(rec.snapshots()))
	}
	if time.Since(start) > 2*time.Second {
		t.Fatalf("stream took too long: %v", time.Since(start))
	}
}

func TestUnit_Streaming_ProviderErrorMidStream(t *testing.T) {
	t.Parallel()
	stub := &streamStubProvider{
		name: "openai", models: []string{"gpt-4o"},
		chunks: []string{
			"data: {\"choices\":[{\"delta\":{\"content\":\"1\"}}]}\n\n",
			"data: {\"choices\":[{\"delta\":{\"content\":\"2\"}}]}\n\n",
			"data: {\"choices\":[{\"delta\":{\"content\":\"3\"}}]}\n\n",
		},
		failAfter: 3,
	}
	handler := newStreamTestHandler(t, stub)
	rec := postChat(t, handler, chatRequestOpts{
		body:    `{"model":"gpt-4o","messages":[{"role":"user","content":"hi"}],"stream":true}`,
		auth:    true,
		agentID: testChatAgentID,
	})
	stub.wg.Wait()
	if rec.Code != http.StatusOK {
		t.Fatalf("status: %d", rec.Code)
	}
	body := rec.Body.String()
	if !strings.Contains(body, "\"1\"") || !strings.Contains(body, "\"3\"") {
		t.Fatalf("partial body: %s", body)
	}
	if strings.Contains(body, "[DONE]") {
		t.Fatal("unexpected [DONE] on incomplete stream")
	}
}

func TestUnit_Streaming_ClientDisconnect(t *testing.T) {
	t.Parallel()
	before := runtime.NumGoroutine()
	entered := make(chan struct{})
	stub := &streamStubProvider{
		name: "openai", models: []string{"gpt-4o"},
		chunks:  []string{"data: {\"choices\":[{\"delta\":{\"content\":\"x\"}}]}\n\n"},
		hang:    true,
		entered: entered,
	}
	handler := newStreamTestHandler(t, stub)

	ctx, cancel := context.WithCancel(context.Background())
	req := newStreamChatRequest(ctx)
	done := make(chan struct{})
	go func() {
		handler.ServeHTTP(httptest.NewRecorder(), req)
		close(done)
	}()
	select {
	case <-entered:
	case <-time.After(2 * time.Second):
		t.Fatal("stub did not enter hang")
	}
	cancel()
	select {
	case <-done:
	case <-time.After(2 * time.Second):
		t.Fatal("handler did not return after client cancel")
	}
	stub.wg.Wait()
	after := runtime.NumGoroutine()
	if after > before+20 {
		t.Fatalf("possible goroutine leak: before=%d after=%d", before, after)
	}
}

func TestUnit_ChatCompletions_streamTrueForwardsSSE(t *testing.T) {
	t.Parallel()
	stub := &streamStubProvider{
		name: "openai", models: []string{"gpt-4o"},
		chunks: []string{
			"data: {\"choices\":[{\"delta\":{\"content\":\"ok\"}}]}\n\n",
			"data: [DONE]\n\n",
		},
	}
	handler := newStreamTestHandlerWithValidator(t, stub,
		&chatMockValidator{res: &auth.ValidateResult{OrgID: uuid.MustParse(testChatOrgID), Permissions: permissions.ProxyChatCompletion}})
	rec := postChat(t, handler, chatRequestOpts{
		body:    `{"model":"gpt-4o","messages":[{"role":"user","content":"hi"}],"stream":true}`,
		auth:    true,
		agentID: testChatAgentID,
	})
	stub.wg.Wait()
	if rec.Code != http.StatusOK {
		t.Fatalf("status: %d body=%s", rec.Code, rec.Body.String())
	}
}

type deadlineRecorder struct {
	*httptest.ResponseRecorder
	deadline time.Time
	called   bool
}

func (d *deadlineRecorder) SetWriteDeadline(t time.Time) error {
	d.called = true
	d.deadline = t
	return nil
}

func TestUnit_ClearSSEWriteDeadline(t *testing.T) {
	t.Parallel()

	rec := &deadlineRecorder{ResponseRecorder: httptest.NewRecorder()}

	clearSSEWriteDeadline(context.Background(), rec, logger.Discard("proxy"))

	if !rec.called {
		t.Fatal("expected SetWriteDeadline call")
	}
	if !rec.deadline.IsZero() {
		t.Fatalf("deadline=%v want zero", rec.deadline)
	}
}

func TestUnit_ClearSSEWriteDeadline_Unsupported(t *testing.T) {
	t.Parallel()

	rec := httptest.NewRecorder()

	clearSSEWriteDeadline(context.Background(), rec, logger.Discard("proxy"))
}

type errDeadlineRecorder struct {
	*httptest.ResponseRecorder
}

func (e *errDeadlineRecorder) SetWriteDeadline(time.Time) error {
	return errors.New("deadline boom")
}

func TestUnit_ClearSSEWriteDeadline_UnexpectedError(t *testing.T) {
	t.Parallel()

	rec := &errDeadlineRecorder{ResponseRecorder: httptest.NewRecorder()}

	clearSSEWriteDeadline(context.Background(), rec, logger.Discard("proxy"))
}
