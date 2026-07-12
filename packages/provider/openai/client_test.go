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
	"strconv"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/prometheus/client_golang/prometheus"
)

func TestOpenAIClient_NonStreaming_Success(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer test-key" {
			t.Errorf("auth header: %q", r.Header.Get("Authorization"))
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
	defer func() { _ = resp.Body.Close() }()
	body, _ := io.ReadAll(resp.Body)
	if !strings.Contains(string(body), "assistant") {
		t.Fatalf("body: %s", body)
	}
}

func TestOpenAIClient_Retry_onRetryableStatus(t *testing.T) {
	t.Parallel()
	for _, tc := range []retryStatusCase{
		{name: "503", failUntil: 2, status: http.StatusServiceUnavailable, wantCalls: 2},
		{name: "429", failUntil: 3, status: http.StatusTooManyRequests, setHeader: true, wantCalls: 3},
	} {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			runRetryStatusCase(t, tc)
		})
	}
}

type retryStatusCase struct {
	name      string
	failUntil int32
	status    int
	setHeader bool
	wantCalls int32
}

func runRetryStatusCase(t *testing.T, tc retryStatusCase) {
	t.Helper()
	var calls atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if calls.Add(1) < tc.failUntil {
			if tc.setHeader {
				w.Header().Set("Retry-After", "0")
			}
			w.WriteHeader(tc.status)
			return
		}
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"choices":[{"message":{"content":"ok"}}]}`))
	}))
	t.Cleanup(srv.Close)

	client := testClient(t, srv.URL, "test-key", nil)
	client.cfg.MaxRetries = intPtr(3)
	client.cfg.RetryBaseDelay = 1 * time.Millisecond

	_, err := client.Complete(context.Background(), provider.Request{
		Model:    "gpt-4o",
		Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
	if err != nil {
		t.Fatalf("Complete: %v", err)
	}
	if calls.Load() != tc.wantCalls {
		t.Fatalf("calls: got %d want %d", calls.Load(), tc.wantCalls)
	}
}

func TestOpenAIClient_RetryableTransport_recordsErrorMetricPerAttempt(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {}))
	url := srv.URL
	srv.Close()

	reg := metrics.NewProxy("test")
	client := testClient(t, url, "test-key", reg)
	client.cfg.MaxRetries = intPtr(2)

	_, err := client.Complete(context.Background(), provider.Request{
		Model:    "gpt-4o",
		Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
	if err == nil {
		t.Fatal("expected transport error")
	}

	body := scrapeProviderMetrics(t, reg.Gatherer())
	if got := countPrometheusCounter(body, `ibex_proxy_provider_requests_total{provider="openai",status_class="error"} `); got != 3 {
		t.Fatalf("provider error attempts: got %d want 3; metrics:\n%s", got, body)
	}
	if got := countPrometheusCounter(body, `ibex_proxy_provider_retries_total{provider="openai"} `); got != 2 {
		t.Fatalf("provider retries: got %d want 2; metrics:\n%s", got, body)
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

func TestOpenAIClient_NonRetryableTransport_recordsSingleErrorMetric(t *testing.T) {
	t.Parallel()
	reg := metrics.NewProxy("test")
	client := testClient(t, "http://127.0.0.1:1", "test-key", reg)
	client.cfg.MaxRetries = intPtr(0)

	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	_, err := client.Complete(ctx, provider.Request{
		Model:    "gpt-4o",
		Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
	if err == nil {
		t.Fatal("expected transport error")
	}

	body := scrapeProviderMetrics(t, reg.Gatherer())
	if got := countPrometheusCounter(body, `ibex_proxy_provider_requests_total{provider="openai",status_class="error"} `); got != 1 {
		t.Fatalf("provider error metric count: got %d want 1; metrics:\n%s", got, body)
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
	client := New(Config{APIKey: secret, BaseURL: srv.URL, Timeout: 5 * time.Second, MaxRetries: intPtr(0)}, log, telemetry.NoopTracer("openai"), nil)
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

func scrapeProviderMetrics(t *testing.T, gatherer prometheus.Gatherer) string {
	t.Helper()
	rec := httptest.NewRecorder()
	metrics.Handler(gatherer).ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/metrics", nil))
	if rec.Code != http.StatusOK {
		t.Fatalf("metrics status: %d", rec.Code)
	}
	return rec.Body.String()
}

func countPrometheusCounter(body, needle string) int {
	idx := strings.Index(body, needle)
	if idx < 0 {
		return 0
	}
	rest := body[idx+len(needle):]
	end := strings.IndexByte(rest, '\n')
	if end < 0 {
		end = len(rest)
	}
	val, err := strconv.Atoi(strings.TrimSpace(rest[:end]))
	if err != nil {
		return 0
	}
	return val
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
		MaxRetries:     intPtr(3),
		RetryBaseDelay: 1 * time.Millisecond,
	}, logger.Discard("openai"), telemetry.NoopTracer("openai"), m)
}
