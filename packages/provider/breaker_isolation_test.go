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

	okBodyOpenAI := `{"choices":[{"message":{"role":"assistant","content":"ok"}}],"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}`
	okBodyAnthropic := `{"id":"msg_1","type":"message","role":"assistant","content":[{"type":"text","text":"ok"}],"model":"claude-sonnet-4-5","stop_reason":"end_turn","usage":{"input_tokens":1,"output_tokens":1}}`

	failSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = io.WriteString(w, `{"error":{"message":"boom"}}`)
	}))
	t.Cleanup(failSrv.Close)

	okSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if r.URL.Path == "/v1/messages" {
			_, _ = io.WriteString(w, okBodyAnthropic)
			return
		}
		_, _ = io.WriteString(w, okBodyOpenAI)
	}))
	t.Cleanup(okSrv.Close)

	cool := time.Minute
	anthBr, err := circuitbreaker.New(circuitbreaker.Settings{
		Name: "anthropic", Window: time.Minute, BucketPeriod: time.Minute,
		MinSamples: 2, FailureRateThreshold: 0.5, CoolDown: cool,
	})
	if err != nil {
		t.Fatal(err)
	}
	oaiBr, err := circuitbreaker.New(circuitbreaker.Settings{
		Name: "openai", Window: time.Minute, BucketPeriod: time.Minute,
		MinSamples: 10, FailureRateThreshold: 0.5, CoolDown: cool,
	})
	if err != nil {
		t.Fatal(err)
	}
	shBr, err := circuitbreaker.New(circuitbreaker.Settings{
		Name: "openaicompatible", MaxFailures: 5, CoolDown: cool,
	})
	if err != nil {
		t.Fatal(err)
	}

	zero := 0
	log := logger.Discard("t")
	tr := telemetry.NoopTracer("t")

	anthFail := anthropic.New(anthropic.Config{
		APIKey: "k", BaseURL: failSrv.URL, MaxRetries: &zero, Breaker: anthBr,
	}, log, tr, nil)
	anthOK := anthropic.New(anthropic.Config{
		APIKey: "k", BaseURL: okSrv.URL, MaxRetries: &zero, Breaker: anthBr,
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

	anthReq := provider.Request{
		Model:    "claude-sonnet-4-5",
		Messages: []provider.Message{{Role: "user", Content: "hi"}},
	}
	oaiReq := provider.Request{
		Model:    "gpt-4o",
		Messages: []provider.Message{{Role: "user", Content: "hi"}},
	}
	shReq := provider.Request{
		Model:    "local-m",
		Messages: []provider.Message{{Role: "user", Content: "hi"}},
	}

	// Trip Anthropic rolling breaker (2 failures @ 100% ≥ 50% with MinSamples=2).
	for i := 0; i < 2; i++ {
		_, _ = anthFail.Complete(context.Background(), anthReq)
	}
	_, err = anthOK.Complete(context.Background(), anthReq)
	var pe *provider.ProviderError
	if !errors.As(err, &pe) || pe.Reason != provider.ErrorReasonCircuitOpen {
		t.Fatalf("anthropic want circuit_open, got %v", err)
	}
	if pe.RetryAfter != cool {
		t.Fatalf("anthropic RetryAfter=%v", pe.RetryAfter)
	}

	resp, err := oai.Complete(context.Background(), oaiReq)
	if err != nil {
		t.Fatalf("openai affected by anthropic breaker: %v", err)
	}
	_ = resp.Body.Close()

	resp, err = sh.Complete(context.Background(), shReq)
	if err != nil {
		t.Fatalf("self-hosted affected by anthropic breaker: %v", err)
	}
	_ = resp.Body.Close()
}
