package openaicompatible

import (
	"context"
	"errors"
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
)

func TestClient_DefaultsProviderNameAndNoopMetrics(t *testing.T) {
	t.Parallel()
	c := New(Config{BaseURL: "http://127.0.0.1:9/v1"}, logger.Discard("t"), telemetry.NoopTracer("t"), nil)
	if c.Name() != ProviderNameSelfHosted {
		t.Fatalf("Name=%q", c.Name())
	}
	var n noopMetrics
	n.IncProviderRequest("x", "2xx")
	n.IncProviderRetry("x")
	n.ObserveProviderDurationSeconds("x", 0.01)
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

func TestEnrichRetryAfter_ClampsOversized(t *testing.T) {
	t.Parallel()
	pe := &provider.ProviderError{
		StatusCode:   http.StatusTooManyRequests,
		ProviderBody: []byte(`{"error":{"retry_after":1e20}}`),
	}
	out := enrichOpenAIRetryAfter(pe)
	var got *provider.ProviderError
	if !errors.As(out, &got) {
		t.Fatalf("got=%v", out)
	}
	if got.RetryAfter != maxRetryBackoff {
		t.Fatalf("RetryAfter=%s want %s", got.RetryAfter, maxRetryBackoff)
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
