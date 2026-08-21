package openaicompatible

import (
	"bytes"
	"context"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/circuitbreaker"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
)

func TestClient_QueueFullReasonOn503(t *testing.T) {
	t.Parallel()
	srv := statusServer(t, http.StatusServiceUnavailable, `{"error":{"message":"queue full"}}`)
	c := newSelfHostedTestClient(srv.URL, nil)
	_, err := completeHi(c)
	requireProviderReason(t, err, provider.ErrorReasonQueueFull)
	mapped, write := provider.MapError(err)
	if !write {
		t.Fatal("expected mapped write")
	}
	if mapped == nil {
		t.Fatal("mapped nil")
	}
	if !strings.Contains(mapped.Detail, "queue") {
		t.Fatalf("mapped=%+v", mapped)
	}
}

func TestClient_OpenAI503HasEmptyReason(t *testing.T) {
	t.Parallel()
	srv := statusServer(t, http.StatusServiceUnavailable, `{"error":{"message":"unavailable"}}`)
	c := New(Config{
		ProviderName:  ProviderNameOpenAI,
		APIKey:        "k",
		BaseURL:       srv.URL,
		MaxRetries:    zeroRetries(),
		AuthMode:      AuthBearerAlways,
		BuiltInModels: []string{"gpt-4o"},
	}, logger.Discard("t"), telemetry.NoopTracer("t"), nil)
	_, err := c.Complete(context.Background(), provider.Request{
		Model: "gpt-4o", Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
	var pe *provider.ProviderError
	if !errors.As(err, &pe) {
		t.Fatalf("err=%v", err)
	}
	if pe.Reason != "" {
		t.Fatalf("Reason=%q want empty", pe.Reason)
	}
}

func TestClient_CircuitBreakerMapsOpen(t *testing.T) {
	t.Parallel()
	srv := statusServer(t, http.StatusInternalServerError, `{"error":{"message":"boom"}}`)
	br := circuitbreaker.New(circuitbreaker.Settings{Name: "t", MaxFailures: 1, CoolDown: time.Minute})
	c := newSelfHostedTestClient(srv.URL, br)
	req := provider.Request{Model: "m", Messages: []provider.Message{{Role: "user", Content: "hi"}}}
	_, _ = c.Complete(context.Background(), req)
	_, err := c.Complete(context.Background(), req)
	requireProviderReason(t, err, provider.ErrorReasonCircuitOpen)
	mapped, _ := provider.MapError(err)
	if mapped == nil {
		t.Fatal("mapped nil")
	}
	if !strings.Contains(mapped.Detail, "circuit") {
		t.Fatalf("mapped=%+v", mapped)
	}
}

func TestClient_BreakerPassesProviderError(t *testing.T) {
	t.Parallel()
	srv := statusServer(t, http.StatusBadRequest, `{"error":{"message":"bad"}}`)
	br := circuitbreaker.New(circuitbreaker.Settings{Name: "t", MaxFailures: 10, CoolDown: time.Minute})
	_, err := completeHi(newSelfHostedTestClient(srv.URL, br))
	var pe *provider.ProviderError
	if !errors.As(err, &pe) {
		t.Fatalf("err=%v", err)
	}
	if pe.Reason == provider.ErrorReasonCircuitOpen {
		t.Fatal("should not be circuit open")
	}
}

func TestClient_BreakerSuccessPath(t *testing.T) {
	t.Parallel()
	srv := statusServer(t, http.StatusOK, `{"choices":[{"message":{"content":"ok"}}]}`)
	br := circuitbreaker.New(circuitbreaker.Settings{Name: "ok", MaxFailures: 5, CoolDown: time.Minute})
	resp, err := completeHi(newSelfHostedTestClient(srv.URL, br))
	if err != nil {
		t.Fatal(err)
	}
	_ = resp.Body.Close()
}

func TestClient_BreakerNonOpenErrorPassthrough(t *testing.T) {
	t.Parallel()
	c := newSelfHostedTestClient("http://127.0.0.1:9", stubBreaker{err: errors.New("unexpected-breaker")})
	_, err := completeHi(c)
	if err == nil || !strings.Contains(err.Error(), "unexpected-breaker") {
		t.Fatalf("err=%v", err)
	}
}

func TestClient_BreakerInvalidResult(t *testing.T) {
	t.Parallel()
	c := newSelfHostedTestClient("http://127.0.0.1:9", stubBreaker{result: "not-a-response"})
	_, err := completeHi(c)
	if err == nil || !strings.Contains(err.Error(), "unexpected result") {
		t.Fatalf("err=%v", err)
	}
}

func TestClient_TransportError(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {}))
	url := srv.URL
	srv.Close()
	_, err := completeHi(newSelfHostedTestClient(url, nil))
	if err == nil {
		t.Fatal("expected transport error")
	}
}

func TestClient_StreamRequiresEventStream(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"choices":[{"message":{"content":"ok"}}]}`))
	}))
	t.Cleanup(srv.Close)
	c := newSelfHostedTestClient(srv.URL, nil)
	_, err := c.Complete(context.Background(), provider.Request{
		Model: "m", Stream: true, Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
	if err == nil {
		t.Fatal("expected non-event-stream error")
	}
}

func TestClassifyForBreaker_CallerVsUpstreamDeadline(t *testing.T) {
	t.Parallel()
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if !errors.Is(classifyForBreaker(ctx, context.Canceled), context.Canceled) {
		t.Fatal("canceled")
	}

	dead, cancelDead := context.WithTimeout(context.Background(), time.Nanosecond)
	defer cancelDead()
	<-dead.Done()
	if !errors.Is(classifyForBreaker(dead, context.DeadlineExceeded), context.DeadlineExceeded) {
		t.Fatal("caller deadline")
	}

	up := classifyForBreaker(context.Background(), context.DeadlineExceeded)
	if errors.Is(up, context.DeadlineExceeded) {
		t.Fatal("upstream deadline must not match DeadlineExceeded")
	}
	if !strings.Contains(up.Error(), "upstream timed out") {
		t.Fatalf("up=%v", up)
	}
}

func statusServer(t *testing.T, code int, body string) *httptest.Server {
	t.Helper()
	payload := []byte(body)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(code)
		_, _ = io.Copy(w, bytes.NewReader(payload))
	}))
	t.Cleanup(srv.Close)
	return srv
}
