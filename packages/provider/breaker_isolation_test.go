package provider_test

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
	"github.com/Rick1330/ibex-harness/packages/provider/anthropic"
	"github.com/Rick1330/ibex-harness/packages/provider/openai"
	"github.com/Rick1330/ibex-harness/packages/provider/openaicompatible"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
)

// Per-provider isolation: tripping Anthropic must not affect OpenAI or self-hosted.
func TestPerProviderCircuitBreakerIsolation(t *testing.T) {
	t.Parallel()

	failSrv, okSrv := isolationServers(t)
	cool := time.Minute
	anthBr := mustBreaker(t, circuitbreaker.Settings{
		Name: "anthropic", Window: time.Minute, BucketPeriod: time.Minute,
		MinSamples: 2, FailureRateThreshold: 0.5, CoolDown: cool,
	})
	oaiBr := mustBreaker(t, circuitbreaker.Settings{
		Name: "openai", Window: time.Minute, BucketPeriod: time.Minute,
		MinSamples: 10, FailureRateThreshold: 0.5, CoolDown: cool,
	})
	shBr := mustBreaker(t, circuitbreaker.Settings{
		Name: "openaicompatible", MaxFailures: 5, CoolDown: cool,
	})

	zero := 0
	log := logger.Discard("t")
	tr := telemetry.NoopTracer("t")
	anthFail := anthropic.New(anthropic.Config{
		APIKey: "k", BaseURL: failSrv.URL, MaxRetries: &zero, Breaker: anthBr,
	}, log, tr, nil)
	oai := openai.New(openai.Config{
		APIKey: "k", BaseURL: okSrv.URL + "/v1", MaxRetries: &zero, Breaker: oaiBr,
	}, log, tr, nil)
	sh := openaicompatible.New(openaicompatible.Config{
		ProviderName: openaicompatible.ProviderNameSelfHosted,
		APIKey:       "", BaseURL: okSrv.URL + "/v1", MaxRetries: &zero,
		AuthMode: openaicompatible.AuthBearerOmitEmpty, ExtraModels: []string{"local-m"},
		Breaker: shBr,
	}, log, tr, nil)

	tripAnthropicBreaker(t, anthFail, cool)
	assertCompleteOK(t, oai, provider.Request{
		Model: "gpt-4o", Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
	assertCompleteOK(t, sh, provider.Request{
		Model: "local-m", Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
}

func isolationServers(t *testing.T) (failSrv, okSrv *httptest.Server) {
	t.Helper()
	okBodyOpenAI := `{"choices":[{"message":{"role":"assistant","content":"ok"}}],"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}`
	okBodyAnthropic := `{"id":"msg_1","type":"message","role":"assistant","content":[{"type":"text","text":"ok"}],"model":"claude-sonnet-4-5","stop_reason":"end_turn","usage":{"input_tokens":1,"output_tokens":1}}`

	failSrv = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = io.WriteString(w, `{"error":{"message":"boom"}}`)
	}))
	t.Cleanup(failSrv.Close)

	okSrv = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if r.URL.Path == "/v1/messages" {
			_, _ = io.WriteString(w, okBodyAnthropic)
			return
		}
		_, _ = io.WriteString(w, okBodyOpenAI)
	}))
	t.Cleanup(okSrv.Close)
	return failSrv, okSrv
}

func mustBreaker(t *testing.T, s circuitbreaker.Settings) *circuitbreaker.Breaker {
	t.Helper()
	br, err := circuitbreaker.New(s)
	if err != nil {
		t.Fatal(err)
	}
	return br
}

func tripAnthropicBreaker(t *testing.T, c *anthropic.Client, cool time.Duration) {
	t.Helper()
	req := provider.Request{
		Model:    "claude-sonnet-4-5",
		Messages: []provider.Message{{Role: "user", Content: "hi"}},
	}
	for i := 0; i < 2; i++ {
		_, _ = c.Complete(context.Background(), req)
	}
	_, err := c.Complete(context.Background(), req)
	var pe *provider.ProviderError
	if !errors.As(err, &pe) {
		t.Fatalf("anthropic want circuit_open, got %v", err)
	}
	if pe.Reason != provider.ErrorReasonCircuitOpen {
		t.Fatalf("Reason=%q", pe.Reason)
	}
	if pe.RetryAfter != cool {
		t.Fatalf("RetryAfter=%v", pe.RetryAfter)
	}
}

func assertCompleteOK(t *testing.T, p provider.Provider, req provider.Request) {
	t.Helper()
	resp, err := p.Complete(context.Background(), req)
	if err != nil {
		t.Fatalf("%s affected by anthropic breaker: %v", p.Name(), err)
	}
	_ = resp.Body.Close()
}
