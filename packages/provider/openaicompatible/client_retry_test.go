package openaicompatible

import (
	"context"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
)

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
	if m.requests.Load() < 2 || m.retries.Load() < 1 || m.durations.Load() < 2 {
		t.Fatalf("requests=%d retries=%d durations=%d", m.requests.Load(), m.retries.Load(), m.durations.Load())
	}
}
