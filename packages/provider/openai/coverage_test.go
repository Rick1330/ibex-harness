package openai

import (
	"context"
	"net/http"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
)

func TestClient_SupportedModels(t *testing.T) {
	t.Parallel()
	c := New(Config{APIKey: "k", BaseURL: "http://example.com"}, logger.Discard("openai"), telemetry.NoopTracer("openai"), nil)
	models := c.SupportedModels()
	if len(models) != 4 {
		t.Fatalf("models: %v", models)
	}
}

func TestConfig_ApplyDefaults_negativeRetriesClamped(t *testing.T) {
	t.Parallel()
	cfg := Config{MaxRetries: -1}
	cfg.ApplyDefaults()
	if cfg.MaxRetries != defaultMaxRetries {
		t.Fatalf("max retries: %d", cfg.MaxRetries)
	}
}

func TestToOpenAIRequest_passthroughFields(t *testing.T) {
	t.Parallel()
	out, err := toOpenAIRequest(provider.Request{
		Model: "gpt-4o",
		Messages: []provider.Message{
			{Role: "user", Content: "hi"},
		},
		PassthroughFields: map[string]any{"top_p": 0.9},
	})
	if err != nil {
		t.Fatalf("toOpenAIRequest: %v", err)
	}
	if out.Model != "gpt-4o" {
		t.Fatalf("model: %q", out.Model)
	}
}

func TestRetryAfterFromProvider_jsonField(t *testing.T) {
	t.Parallel()
	pe := &provider.ProviderError{
		ProviderBody: []byte(`{"error":{"retry_after":2.5}}`),
	}
	if got := retryAfterFromProvider(pe); got != 2500*time.Millisecond {
		t.Fatalf("retry after: %v", got)
	}
}

func TestStatusClass_allBuckets(t *testing.T) {
	t.Parallel()
	if statusClass(http.StatusOK) != "2xx" {
		t.Fatal("expected 2xx")
	}
	if statusClass(http.StatusInternalServerError) != "5xx" {
		t.Fatal("expected 5xx")
	}
	if statusClass(http.StatusBadRequest) != "4xx" {
		t.Fatal("expected 4xx")
	}
	if statusClass(100) != "other" {
		t.Fatal("expected other")
	}
}

func TestRetryAfterHeader_httpDate(t *testing.T) {
	t.Parallel()
	future := time.Now().Add(60 * time.Second).UTC().Format(http.TimeFormat)
	if got := RetryAfterHeader(future); got <= 0 {
		t.Fatalf("retry after: %v", got)
	}
}

func TestNoopMetrics(t *testing.T) {
	t.Parallel()
	var m Metrics = noopMetrics{}
	m.IncProviderRequest("openai", "2xx")
	m.IncProviderRetry("openai")
}

func TestNew_nilDepsUseDefaults(t *testing.T) {
	t.Parallel()
	c := New(Config{APIKey: "k", BaseURL: "http://example.com"}, logger.Discard("openai"), nil, nil)
	if c == nil || c.tracer == nil || c.metrics == nil {
		t.Fatal("expected defaults for nil tracer and metrics")
	}
}

func TestWaitBeforeRetry_contextCanceled(t *testing.T) {
	t.Parallel()
	client := testClient(t, "http://example.com", "k", nil)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	err := client.waitBeforeRetry(ctx, 1, &provider.ProviderError{StatusCode: http.StatusTooManyRequests})
	if err == nil {
		t.Fatal("expected context error")
	}
}

func TestIsRetryableTransport_timeout(t *testing.T) {
	t.Parallel()
	var netErr timeoutNetError
	if !isRetryableTransport(netErr) {
		t.Fatal("timeout net error should retry")
	}
}

type timeoutNetError struct{}

func (timeoutNetError) Error() string   { return "timeout" }
func (timeoutNetError) Timeout() bool   { return true }
func (timeoutNetError) Temporary() bool { return false }
