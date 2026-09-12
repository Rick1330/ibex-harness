package anthropic

import (
	"context"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/circuitbreaker"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
)

func TestClient_CircuitBreakerMapsOpenWithRetryAfter(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = io.WriteString(w, `{"error":{"type":"api_error","message":"boom"}}`)
	}))
	t.Cleanup(srv.Close)

	cool := 45 * time.Second
	br, err := circuitbreaker.New(circuitbreaker.Settings{
		Name: "anthropic", MaxFailures: 1, CoolDown: cool,
	})
	if err != nil {
		t.Fatal(err)
	}
	zero := 0
	c := New(Config{
		APIKey: "k", BaseURL: srv.URL, MaxRetries: &zero, Breaker: br,
	}, logger.Discard("t"), telemetry.NoopTracer("t"), nil)

	req := provider.Request{
		Model:    modelClaudeSonnet45,
		Messages: []provider.Message{{Role: "user", Content: "hi"}},
	}
	_, _ = c.Complete(context.Background(), req)
	_, err = c.Complete(context.Background(), req)
	assertCircuitOpenRetryAfter(t, err, cool)
}

func assertCircuitOpenRetryAfter(t *testing.T, err error, cool time.Duration) {
	t.Helper()
	var pe *provider.ProviderError
	if !errors.As(err, &pe) {
		t.Fatalf("err=%v", err)
	}
	if pe.Reason != provider.ErrorReasonCircuitOpen {
		t.Fatalf("Reason=%q", pe.Reason)
	}
	if pe.RetryAfter != cool {
		t.Fatalf("RetryAfter=%v want %v", pe.RetryAfter, cool)
	}
	mapped, write := provider.MapError(err)
	if !write {
		t.Fatal("want write")
	}
	if mapped == nil {
		t.Fatal("mapped nil")
	}
	if mapped.RetryAfter != cool {
		t.Fatalf("mapped RetryAfter=%v", mapped.RetryAfter)
	}
}
