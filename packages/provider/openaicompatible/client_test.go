package openaicompatible

import (
	"bytes"
	"context"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/circuitbreaker"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
)

func TestClient_NonStreaming_Success_OmitEmptyAuth(t *testing.T) {
	t.Parallel()
	var sawAuth string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		sawAuth = r.Header.Get("Authorization")
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"choices":[{"message":{"content":"ok"}}]}`))
	}))
	t.Cleanup(srv.Close)

	zero := 0
	c := New(Config{
		ProviderName: ProviderNameSelfHosted,
		BaseURL:      srv.URL,
		Timeout:      5 * time.Second,
		MaxRetries:   &zero,
		ExtraModels:  []string{"local-model"},
		AuthMode:     AuthBearerOmitEmpty,
	}, logger.Discard("t"), telemetry.NoopTracer("t"), nil)

	if c.Name() != ProviderNameSelfHosted {
		t.Fatalf("Name=%q", c.Name())
	}
	models := c.SupportedModels()
	if len(models) != 1 || models[0] != "local-model" {
		t.Fatalf("SupportedModels=%v", models)
	}

	resp, err := c.Complete(context.Background(), provider.Request{
		Model: "local-model", Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
	if err != nil {
		t.Fatalf("Complete: %v", err)
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	if !strings.Contains(string(body), "ok") {
		t.Fatalf("body=%s", body)
	}
	if sawAuth != "" {
		t.Fatalf("expected no Authorization, got %q", sawAuth)
	}
}

func TestClient_BearerWhenKeySet(t *testing.T) {
	t.Parallel()
	var sawAuth string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		sawAuth = r.Header.Get("Authorization")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"choices":[{"message":{"content":"ok"}}]}`))
	}))
	t.Cleanup(srv.Close)
	zero := 0
	c := New(Config{
		ProviderName: ProviderNameSelfHosted,
		APIKey:       "secret",
		BaseURL:      srv.URL,
		MaxRetries:   &zero,
		AuthMode:     AuthBearerOmitEmpty,
		ExtraModels:  []string{"m"},
	}, logger.Discard("t"), telemetry.NoopTracer("t"), nil)
	_, err := c.Complete(context.Background(), provider.Request{
		Model: "m", Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
	if err != nil {
		t.Fatalf("Complete: %v", err)
	}
	if sawAuth != "Bearer secret" {
		t.Fatalf("auth=%q", sawAuth)
	}
}

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

func TestClient_RetryOn429(t *testing.T) {
	t.Parallel()
	var calls atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		if calls.Add(1) < 2 {
			w.Header().Set("Retry-After", "0")
			w.WriteHeader(http.StatusTooManyRequests)
			_, _ = w.Write([]byte(`{"error":{"message":"slow","retry_after":0.001}}`))
			return
		}
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"choices":[{"message":{"content":"ok"}}]}`))
	}))
	t.Cleanup(srv.Close)
	retries := 3
	c := New(Config{
		ProviderName:   ProviderNameSelfHosted,
		BaseURL:        srv.URL,
		MaxRetries:     &retries,
		RetryBaseDelay: time.Millisecond,
		AuthMode:       AuthBearerOmitEmpty,
		ExtraModels:    []string{"m"},
	}, logger.Discard("t"), telemetry.NoopTracer("t"), nil)
	_, err := c.Complete(context.Background(), provider.Request{
		Model: "m", Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
	if err != nil {
		t.Fatalf("Complete: %v", err)
	}
	if calls.Load() != 2 {
		t.Fatalf("calls=%d", calls.Load())
	}
}

func TestClient_NonRetryable400(t *testing.T) {
	t.Parallel()
	var calls atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		calls.Add(1)
		w.WriteHeader(http.StatusBadRequest)
		_, _ = w.Write([]byte(`{"error":{"message":"bad"}}`))
	}))
	t.Cleanup(srv.Close)
	retries := 3
	c := New(Config{
		ProviderName: ProviderNameSelfHosted,
		BaseURL:      srv.URL,
		MaxRetries:   &retries,
		AuthMode:     AuthBearerOmitEmpty,
		ExtraModels:  []string{"m"},
	}, logger.Discard("t"), telemetry.NoopTracer("t"), nil)
	_, err := c.Complete(context.Background(), provider.Request{
		Model: "m", Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
	if err == nil {
		t.Fatal("expected error")
	}
	if calls.Load() != 1 {
		t.Fatalf("calls=%d", calls.Load())
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

func TestClient_AlwaysAuthMode(t *testing.T) {
	t.Parallel()
	var sawAuth string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		sawAuth = r.Header.Get("Authorization")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"choices":[{"message":{"content":"ok"}}]}`))
	}))
	t.Cleanup(srv.Close)
	zero := 0
	c := New(Config{
		ProviderName: ProviderNameOpenAI,
		APIKey:       "k",
		BaseURL:      srv.URL,
		MaxRetries:   &zero,
		AuthMode:     AuthBearerAlways,
		BuiltInModels: []string{"gpt-4o"},
	}, logger.Discard("t"), telemetry.NoopTracer("t"), nil)
	_, err := c.Complete(context.Background(), provider.Request{
		Model: "gpt-4o", Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
	if err != nil {
		t.Fatalf("Complete: %v", err)
	}
	if sawAuth != "Bearer k" {
		t.Fatalf("auth=%q", sawAuth)
	}
}

func TestClient_DefaultsProviderNameAndNoopMetrics(t *testing.T) {
	t.Parallel()
	c := New(Config{BaseURL: "http://127.0.0.1:9/v1"}, logger.Discard("t"), telemetry.NoopTracer("t"), nil)
	if c.Name() != ProviderNameSelfHosted {
		t.Fatalf("Name=%q", c.Name())
	}
	var n noopMetrics
	n.IncProviderRequest("x", "2xx")
	n.IncProviderRetry("x")
}

func TestClient_ApplyDefaults_NegativeRetries(t *testing.T) {
	t.Parallel()
	neg := -1
	cfg := Config{MaxRetries: &neg, Timeout: -1, StreamTimeout: -1, RetryBaseDelay: -1}
	cfg.ApplyDefaults()
	if *cfg.MaxRetries != 0 {
		t.Fatalf("MaxRetries=%d", *cfg.MaxRetries)
	}
	if cfg.Timeout <= 0 || cfg.StreamTimeout <= 0 || cfg.RetryBaseDelay <= 0 {
		t.Fatal("defaults not applied")
	}
	if cfg.maxRetries() != 0 {
		t.Fatal("maxRetries")
	}
	cfg2 := Config{}
	if cfg2.maxRetries() != defaultMaxRetries {
		t.Fatalf("nil maxRetries=%d", cfg2.maxRetries())
	}
}

func TestEnrichRetryAfter_JSONAndPassthrough(t *testing.T) {
	t.Parallel()
	if enrichOpenAIRetryAfter(errors.New("x")) == nil {
		t.Fatal("passthrough")
	}
	pe := &provider.ProviderError{StatusCode: 400, ProviderErrMsg: "n"}
	if enrichOpenAIRetryAfter(pe) != pe {
		t.Fatal("non-429")
	}
	pe429 := &provider.ProviderError{
		StatusCode: http.StatusTooManyRequests, RetryAfter: time.Second,
	}
	if enrichOpenAIRetryAfter(pe429) != pe429 {
		t.Fatal("already set")
	}
	peJSON := &provider.ProviderError{
		StatusCode:   http.StatusTooManyRequests,
		ProviderBody: []byte(`{"error":{"retry_after":1.5}}`),
	}
	out := enrichOpenAIRetryAfter(peJSON)
	var got *provider.ProviderError
	if !errors.As(out, &got) || got.RetryAfter <= 0 {
		t.Fatalf("got=%v", out)
	}
}

func TestExtractOpenAIErrorMessage_Fallback(t *testing.T) {
	t.Parallel()
	if extractOpenAIErrorMessage([]byte(`not-json`)) != "upstream provider error" {
		t.Fatal("fallback")
	}
	if extractOpenAIErrorMessage([]byte(`{"error":{"message":"x"}}`)) != "x" {
		t.Fatal("message")
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

type stubBreaker struct{ err error }

func (s stubBreaker) Execute(fn func() (any, error)) (any, error) {
	if s.err != nil {
		return nil, s.err
	}
	return fn()
}

type countingMetrics struct {
	requests atomic.Int32
	retries  atomic.Int32
}

func (m *countingMetrics) IncProviderRequest(string, string) { m.requests.Add(1) }
func (m *countingMetrics) IncProviderRetry(string)           { m.retries.Add(1) }

func TestClient_RecordsMetricsOnRetry(t *testing.T) {
	t.Parallel()
	var calls atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		if calls.Add(1) < 2 {
			w.WriteHeader(http.StatusServiceUnavailable)
			return
		}
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"choices":[{"message":{"content":"ok"}}]}`))
	}))
	t.Cleanup(srv.Close)
	retries := 3
	m := &countingMetrics{}
	c := New(Config{
		ProviderName:   ProviderNameSelfHosted,
		BaseURL:        srv.URL,
		MaxRetries:     &retries,
		RetryBaseDelay: time.Millisecond,
		AuthMode:       AuthBearerOmitEmpty,
		ExtraModels:    []string{"m"},
	}, logger.Discard("t"), telemetry.NoopTracer("t"), m)
	_, err := c.Complete(context.Background(), provider.Request{
		Model: "m", Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
	if err != nil {
		t.Fatal(err)
	}
	if m.requests.Load() < 2 || m.retries.Load() < 1 {
		t.Fatalf("requests=%d retries=%d", m.requests.Load(), m.retries.Load())
	}
}

func TestMarshalPassthroughFields(t *testing.T) {
	t.Parallel()
	raw, err := marshalOpenAIRequestBody(provider.Request{
		Model:             "m",
		Messages:          []provider.Message{{Role: "user", Content: "hi"}},
		PassthroughFields: map[string]any{"top_p": 0.9, "model": "denied"},
	})
	if err != nil {
		t.Fatal(err)
	}
	s := string(raw)
	if !strings.Contains(s, `"top_p"`) {
		t.Fatalf("body=%s", s)
	}
	if strings.Count(s, `"model"`) != 1 {
		t.Fatalf("denied model overwrite: %s", s)
	}
}

func TestMarshalPassthrough_CyclicFails(t *testing.T) {
	t.Parallel()
	type node struct{ Next any }
	n := &node{}
	n.Next = n
	_, err := marshalOpenAIRequestBody(provider.Request{
		Model:             "m",
		Messages:          []provider.Message{{Role: "user", Content: "hi"}},
		PassthroughFields: map[string]any{"cycle": n},
	})
	if err == nil {
		t.Fatal("expected marshal error")
	}
	zero := 0
	c := New(Config{
		ProviderName: ProviderNameSelfHosted,
		BaseURL:      "http://127.0.0.1:9",
		MaxRetries:   &zero,
		AuthMode:     AuthBearerOmitEmpty,
		ExtraModels:  []string{"m"},
	}, logger.Discard("t"), telemetry.NoopTracer("t"), nil)
	_, err = c.Complete(context.Background(), provider.Request{
		Model: "m", Messages: []provider.Message{{Role: "user", Content: "hi"}},
		PassthroughFields: map[string]any{"cycle": n},
	})
	if err == nil {
		t.Fatal("expected Complete error")
	}
}

func TestEnrichRetryAfter_NoJSONRetry(t *testing.T) {
	t.Parallel()
	pe := &provider.ProviderError{
		StatusCode:   http.StatusTooManyRequests,
		ProviderBody: []byte(`{"error":{}}`),
	}
	if enrichOpenAIRetryAfter(pe) != pe {
		t.Fatal("expected same pointer when no retry_after")
	}
}

func TestClient_APIKeyNotInLogs(t *testing.T) {
	t.Parallel()
	var buf bytes.Buffer
	log, err := logger.New(logger.Config{Service: "t", Level: slog.LevelDebug, Writer: &buf})
	if err != nil {
		t.Fatal(err)
	}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"choices":[{"message":{"content":"ok"}}]}`))
	}))
	t.Cleanup(srv.Close)
	secret := "sk-never-log-me"
	zero := 0
	c := New(Config{
		ProviderName: ProviderNameSelfHosted,
		APIKey:       secret,
		BaseURL:      srv.URL,
		MaxRetries:   &zero,
		AuthMode:     AuthBearerOmitEmpty,
		ExtraModels:  []string{"m"},
	}, log, telemetry.NoopTracer("t"), nil)
	_, err = c.Complete(context.Background(), provider.Request{
		Model: "m", Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(buf.String(), secret) {
		t.Fatal("secret leaked")
	}
}
