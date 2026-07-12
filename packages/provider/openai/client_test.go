package openai

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
)

func TestOpenAIClient_NonStreaming_Success(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer test-key" {
			t.Fatalf("auth header: %q", r.Header.Get("Authorization"))
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"id":"cmpl-1","choices":[{"message":{"role":"assistant","content":"ok"}}],"usage":{"prompt_tokens":1,"completion_tokens":2,"total_tokens":3}}`))
	}))
	t.Cleanup(srv.Close)

	client := testClient(t, srv.URL, "test-key", nil)
	resp, err := client.Complete(context.Background(), provider.Request{
		Model:    "gpt-4o",
		Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
	if err != nil {
		t.Fatalf("Complete: %v", err)
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	if !strings.Contains(string(body), "assistant") {
		t.Fatalf("body: %s", body)
	}
}

func TestOpenAIClient_Retry_On503(t *testing.T) {
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

	client := testClient(t, srv.URL, "test-key", nil)
	client.cfg.MaxRetries = 2
	client.cfg.RetryBaseDelay = 1 * time.Millisecond

	_, err := client.Complete(context.Background(), provider.Request{
		Model:    "gpt-4o",
		Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
	if err != nil {
		t.Fatalf("Complete: %v", err)
	}
}

func TestOpenAIClient_Retry_On429(t *testing.T) {
	t.Parallel()
	var calls atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if calls.Add(1) < 3 {
			w.Header().Set("Retry-After", "0")
			w.WriteHeader(http.StatusTooManyRequests)
			return
		}
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"choices":[{"message":{"content":"ok"}}]}`))
	}))
	t.Cleanup(srv.Close)

	reg := metrics.NewProxy("test")
	client := testClient(t, srv.URL, "test-key", reg)
	client.cfg.MaxRetries = 3
	client.cfg.RetryBaseDelay = 1 * time.Millisecond

	_, err := client.Complete(context.Background(), provider.Request{
		Model:    "gpt-4o",
		Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
	if err != nil {
		t.Fatalf("Complete: %v", err)
	}
	if calls.Load() != 3 {
		t.Fatalf("calls: %d", calls.Load())
	}
}

func TestOpenAIClient_NoRetry_On400(t *testing.T) {
	t.Parallel()
	var calls atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		calls.Add(1)
		w.WriteHeader(http.StatusBadRequest)
		_, _ = w.Write([]byte(`{"error":{"message":"bad request"}}`))
	}))
	t.Cleanup(srv.Close)

	client := testClient(t, srv.URL, "test-key", nil)
	_, err := client.Complete(context.Background(), provider.Request{
		Model:    "gpt-4o",
		Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
	if err == nil {
		t.Fatal("expected error")
	}
	var pe *provider.ProviderError
	if !errors.As(err, &pe) || pe.StatusCode != http.StatusBadRequest {
		t.Fatalf("err: %v", err)
	}
	if calls.Load() != 1 {
		t.Fatalf("calls: %d", calls.Load())
	}
}

func TestOpenAIClient_Timeout(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		time.Sleep(200 * time.Millisecond)
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(srv.Close)

	client := testClient(t, srv.URL, "test-key", nil)
	client.cfg.Timeout = 50 * time.Millisecond
	client.httpClient.Timeout = 50 * time.Millisecond

	_, err := client.Complete(context.Background(), provider.Request{
		Model:    "gpt-4o",
		Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
	if err == nil {
		t.Fatal("expected timeout error")
	}
}

func TestOpenAIClient_NetworkError(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {}))
	url := srv.URL
	srv.Close()

	client := testClient(t, url, "test-key", nil)
	_, err := client.Complete(context.Background(), provider.Request{
		Model:    "gpt-4o",
		Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
	if err == nil {
		t.Fatal("expected network error")
	}
}

func TestOpenAIClient_APIKeyNotInLogs(t *testing.T) {
	t.Parallel()
	var logBuf bytes.Buffer
	log, err := logger.New(logger.Config{
		Service: "test",
		Level:   slog.LevelDebug,
		Writer:  &logBuf,
	})
	if err != nil {
		t.Fatalf("logger: %v", err)
	}

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"choices":[{"message":{"content":"ok"}}]}`))
	}))
	t.Cleanup(srv.Close)

	secret := "sk-secret-key-not-in-logs"
	client := New(Config{APIKey: secret, BaseURL: srv.URL, Timeout: 5 * time.Second, MaxRetries: 0}, log, telemetry.NoopTracer("openai"), nil)
	_, err = client.Complete(context.Background(), provider.Request{
		Model:    "gpt-4o",
		Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
	if err != nil {
		t.Fatalf("Complete: %v", err)
	}
	if strings.Contains(logBuf.String(), secret) {
		t.Fatalf("API key leaked into logs")
	}
}

func TestToOpenAIRequest_marshalsMessages(t *testing.T) {
	t.Parallel()
	out, err := toOpenAIRequest(provider.Request{
		Model:    "gpt-4o",
		Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
	if err != nil {
		t.Fatalf("toOpenAIRequest: %v", err)
	}
	raw, err := json.Marshal(out)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	if !strings.Contains(string(raw), `"role":"user"`) {
		t.Fatalf("body: %s", raw)
	}
}

func testClient(t *testing.T, baseURL, apiKey string, reg *metrics.ProxyRegistry) *Client {
	t.Helper()
	var m Metrics = noopMetrics{}
	if reg != nil {
		m = reg
	}
	return New(Config{
		APIKey:         apiKey,
		BaseURL:        baseURL,
		Timeout:        5 * time.Second,
		MaxRetries:     3,
		RetryBaseDelay: 1 * time.Millisecond,
	}, logger.Discard("openai"), telemetry.NoopTracer("openai"), m)
}
