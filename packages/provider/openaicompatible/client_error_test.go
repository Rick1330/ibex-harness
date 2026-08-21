package openaicompatible

import (
	"context"
	"errors"
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
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusServiceUnavailable)
		_, _ = w.Write([]byte(`{"error":{"message":"queue full"}}`))
	}))
	t.Cleanup(srv.Close)
	zero := 0
	c := New(Config{
		ProviderName: ProviderNameSelfHosted,
		BaseURL:      srv.URL,
		MaxRetries:   &zero,
		AuthMode:     AuthBearerOmitEmpty,
		ExtraModels:  []string{"m"},
	}, logger.Discard("t"), telemetry.NoopTracer("t"), nil)
	_, err := c.Complete(context.Background(), provider.Request{
		Model: "m", Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
	var pe *provider.ProviderError
	if !errors.As(err, &pe) {
		t.Fatalf("err=%v", err)
	}
	if pe.Reason != provider.ErrorReasonQueueFull {
		t.Fatalf("Reason=%q", pe.Reason)
	}
	mapped, write := provider.MapError(err)
	if !write || mapped == nil || !strings.Contains(mapped.Detail, "queue") {
		t.Fatalf("mapped=%+v", mapped)
	}
}

func TestClient_OpenAI503HasEmptyReason(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusServiceUnavailable)
		_, _ = w.Write([]byte(`{"error":{"message":"unavailable"}}`))
	}))
	t.Cleanup(srv.Close)
	zero := 0
	c := New(Config{
		ProviderName:  ProviderNameOpenAI,
		APIKey:        "k",
		BaseURL:       srv.URL,
		MaxRetries:    &zero,
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
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = w.Write([]byte(`{"error":{"message":"boom"}}`))
	}))
	t.Cleanup(srv.Close)
	zero := 0
	br := circuitbreaker.New(circuitbreaker.Settings{Name: "t", MaxFailures: 1, CoolDown: time.Minute})
	c := New(Config{
		ProviderName: ProviderNameSelfHosted,
		BaseURL:      srv.URL,
		MaxRetries:   &zero,
		AuthMode:     AuthBearerOmitEmpty,
		ExtraModels:  []string{"m"},
		Breaker:      br,
	}, logger.Discard("t"), telemetry.NoopTracer("t"), nil)
	req := provider.Request{Model: "m", Messages: []provider.Message{{Role: "user", Content: "hi"}}}
	_, _ = c.Complete(context.Background(), req) // trip
	_, err := c.Complete(context.Background(), req)
	var pe *provider.ProviderError
	if !errors.As(err, &pe) {
		t.Fatalf("err=%v", err)
	}
	if pe.Reason != provider.ErrorReasonCircuitOpen {
		t.Fatalf("Reason=%q", pe.Reason)
	}
	mapped, _ := provider.MapError(err)
	if mapped == nil || !strings.Contains(mapped.Detail, "circuit") {
		t.Fatalf("mapped=%+v", mapped)
	}
}

func TestClient_BreakerPassesProviderError(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusBadRequest)
		_, _ = w.Write([]byte(`{"error":{"message":"bad"}}`))
	}))
	t.Cleanup(srv.Close)
	zero := 0
	br := circuitbreaker.New(circuitbreaker.Settings{Name: "t", MaxFailures: 10, CoolDown: time.Minute})
	c := New(Config{
		ProviderName: ProviderNameSelfHosted,
		BaseURL:      srv.URL,
		MaxRetries:   &zero,
		AuthMode:     AuthBearerOmitEmpty,
		ExtraModels:  []string{"m"},
		Breaker:      br,
	}, logger.Discard("t"), telemetry.NoopTracer("t"), nil)
	_, err := c.Complete(context.Background(), provider.Request{
		Model: "m", Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
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
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"choices":[{"message":{"content":"ok"}}]}`))
	}))
	t.Cleanup(srv.Close)
	zero := 0
	br := circuitbreaker.New(circuitbreaker.Settings{Name: "ok", MaxFailures: 5, CoolDown: time.Minute})
	c := New(Config{
		ProviderName: ProviderNameSelfHosted,
		BaseURL:      srv.URL,
		MaxRetries:   &zero,
		AuthMode:     AuthBearerOmitEmpty,
		ExtraModels:  []string{"m"},
		Breaker:      br,
	}, logger.Discard("t"), telemetry.NoopTracer("t"), nil)
	resp, err := c.Complete(context.Background(), provider.Request{
		Model: "m", Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
	if err != nil {
		t.Fatal(err)
	}
	_ = resp.Body.Close()
}

func TestClient_BreakerNonOpenErrorPassthrough(t *testing.T) {
	t.Parallel()
	zero := 0
	c := New(Config{
		ProviderName: ProviderNameSelfHosted,
		BaseURL:      "http://127.0.0.1:9",
		MaxRetries:   &zero,
		ExtraModels:  []string{"m"},
		AuthMode:     AuthBearerOmitEmpty,
		Breaker:      stubBreaker{err: errors.New("unexpected-breaker")},
	}, logger.Discard("t"), telemetry.NoopTracer("t"), nil)
	_, err := c.Complete(context.Background(), provider.Request{
		Model: "m", Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
	if err == nil || !strings.Contains(err.Error(), "unexpected-breaker") {
		t.Fatalf("err=%v", err)
	}
}

func TestClient_BreakerInvalidResult(t *testing.T) {
	t.Parallel()
	zero := 0
	c := New(Config{
		ProviderName: ProviderNameSelfHosted,
		BaseURL:      "http://127.0.0.1:9",
		MaxRetries:   &zero,
		ExtraModels:  []string{"m"},
		AuthMode:     AuthBearerOmitEmpty,
		Breaker:      stubBreaker{result: "not-a-response"},
	}, logger.Discard("t"), telemetry.NoopTracer("t"), nil)
	_, err := c.Complete(context.Background(), provider.Request{
		Model: "m", Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
	if err == nil || !strings.Contains(err.Error(), "unexpected result") {
		t.Fatalf("err=%v", err)
	}
}

func TestClient_TransportError(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {}))
	url := srv.URL
	srv.Close()
	zero := 0
	c := New(Config{
		ProviderName: ProviderNameSelfHosted,
		BaseURL:      url,
		MaxRetries:   &zero,
		AuthMode:     AuthBearerOmitEmpty,
		ExtraModels:  []string{"m"},
	}, logger.Discard("t"), telemetry.NoopTracer("t"), nil)
	_, err := c.Complete(context.Background(), provider.Request{
		Model: "m", Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
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
	zero := 0
	c := New(Config{
		ProviderName: ProviderNameSelfHosted,
		BaseURL:      srv.URL,
		MaxRetries:   &zero,
		AuthMode:     AuthBearerOmitEmpty,
		ExtraModels:  []string{"m"},
	}, logger.Discard("t"), telemetry.NoopTracer("t"), nil)
	_, err := c.Complete(context.Background(), provider.Request{
		Model: "m", Stream: true, Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
	if err == nil {
		t.Fatal("expected non-event-stream error")
	}
}
