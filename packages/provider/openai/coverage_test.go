package openai

import (
	"context"
	"net/http"
	"strings"
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

func TestConfig_ApplyDefaults_nilUsesDefaultRetries(t *testing.T) {
	t.Parallel()
	cfg := Config{}
	cfg.ApplyDefaults()
	if cfg.maxRetries() != defaultMaxRetries {
		t.Fatalf("max retries: %d", cfg.maxRetries())
	}
}

func TestConfig_ApplyDefaults_explicitZeroRetriesPreserved(t *testing.T) {
	t.Parallel()
	cfg := Config{MaxRetries: intPtr(0)}
	cfg.ApplyDefaults()
	if cfg.maxRetries() != 0 {
		t.Fatalf("max retries: %d", cfg.maxRetries())
	}
}

func TestConfig_ApplyDefaults_negativeRetriesClampedToZero(t *testing.T) {
	t.Parallel()
	cfg := Config{MaxRetries: intPtr(-1)}
	cfg.ApplyDefaults()
	if cfg.maxRetries() != 0 {
		t.Fatalf("max retries: %d", cfg.maxRetries())
	}
}

func TestToOpenAIRequest_passthroughFields(t *testing.T) {
	t.Parallel()
	raw, err := marshalOpenAIRequestBody(provider.Request{
		Model: "gpt-4o",
		Messages: []provider.Message{
			{Role: "user", Content: "hi"},
		},
		PassthroughFields: map[string]any{"top_p": 0.9},
	})
	if err != nil {
		t.Fatalf("marshalOpenAIRequestBody: %v", err)
	}
	if !strings.Contains(string(raw), `"top_p":0.9`) {
		t.Fatalf("body: %s", raw)
	}
}

func TestToOpenAIRequest_deniesSecurityFieldOverrides(t *testing.T) {
	t.Parallel()
	temp := 0.5
	raw, err := marshalOpenAIRequestBody(provider.Request{
		Model:       "gpt-4o",
		MaxTokens:   100,
		Temperature: &temp,
		Messages:    []provider.Message{{Role: "user", Content: "hi"}},
		PassthroughFields: map[string]any{
			"model":       "evil",
			"messages":    []any{},
			"stream":      true,
			"max_tokens":  9999,
			"temperature": 2.0,
			"top_p":       0.9,
		},
	})
	if err != nil {
		t.Fatalf("marshalOpenAIRequestBody: %v", err)
	}
	body := string(raw)
	for _, tc := range []struct {
		name      string
		fragment  string
		mustExist bool
	}{
		{name: "model preserved", fragment: `"model":"gpt-4o"`, mustExist: true},
		{name: "max_tokens preserved", fragment: `"max_tokens":100`, mustExist: true},
		{name: "temperature preserved", fragment: `"temperature":0.5`, mustExist: true},
		{name: "top_p passthrough", fragment: `"top_p":0.9`, mustExist: true},
		{name: "stream denied", fragment: `"stream":true`, mustExist: false},
		{name: "max_tokens denied", fragment: `"max_tokens":9999`, mustExist: false},
		{name: "temperature denied", fragment: `"temperature":2`, mustExist: false},
	} {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			got := strings.Contains(body, tc.fragment)
			if got != tc.mustExist {
				t.Fatalf("fragment %q exist=%v body=%s", tc.fragment, got, body)
			}
		})
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
	if c == nil {
		t.Fatal("expected client")
	}
	if c.tracer == nil {
		t.Fatal("expected default tracer")
	}
	if c.metrics == nil {
		t.Fatal("expected default metrics")
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

func TestWaitBeforeRetry_honorsProviderRetryAfter(t *testing.T) {
	t.Parallel()
	client := testClient(t, "http://example.com", "k", nil)
	err := client.waitBeforeRetry(context.Background(), 1, &provider.ProviderError{
		StatusCode:   http.StatusTooManyRequests,
		ProviderBody: []byte(`{"error":{"retry_after":0.001}}`),
	})
	if err != nil {
		t.Fatalf("waitBeforeRetry: %v", err)
	}
}

func TestRetryDelay_capsAtMaxBackoff(t *testing.T) {
	t.Parallel()
	got := retryDelay(time.Second, 20)
	if got > maxRetryBackoff {
		t.Fatalf("delay %v exceeds max %v", got, maxRetryBackoff)
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
