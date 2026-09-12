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

// Per-provider isolation: tripping any one breaker must not affect the other two.
func TestPerProviderCircuitBreakerIsolation(t *testing.T) {
	t.Parallel()
	failSrv, okSrv := isolationServers(t)

	t.Run("trip_anthropic", func(t *testing.T) {
		t.Parallel()
		fx := newIsolationFixture(t, failSrv, okSrv)
		tripProviderBreaker(t, fx.anthFail, fx.anthReq, fx.cool, 2)
		assertCompleteOK(t, fx.oaiOK, fx.oaiReq)
		assertCompleteOK(t, fx.shOK, fx.shReq)
	})
	t.Run("trip_openai", func(t *testing.T) {
		t.Parallel()
		fx := newIsolationFixture(t, failSrv, okSrv)
		tripProviderBreaker(t, fx.oaiFail, fx.oaiReq, fx.cool, 2)
		assertCompleteOK(t, fx.anthOK, fx.anthReq)
		assertCompleteOK(t, fx.shOK, fx.shReq)
	})
	t.Run("trip_selfhosted", func(t *testing.T) {
		t.Parallel()
		fx := newIsolationFixture(t, failSrv, okSrv)
		tripProviderBreaker(t, fx.shFail, fx.shReq, fx.cool, 2)
		assertCompleteOK(t, fx.anthOK, fx.anthReq)
		assertCompleteOK(t, fx.oaiOK, fx.oaiReq)
	})
}

type isolationFixture struct {
	cool                   time.Duration
	anthFail, anthOK       provider.Provider
	oaiFail, oaiOK         provider.Provider
	shFail, shOK           provider.Provider
	anthReq, oaiReq, shReq provider.Request
}

func newIsolationFixture(t *testing.T, failSrv, okSrv *httptest.Server) isolationFixture {
	t.Helper()
	cool := time.Minute
	zero := 0
	log := logger.Discard("t")
	tr := telemetry.NoopTracer("t")
	suffix := t.Name()

	anthBr := mustBreaker(t, circuitbreaker.Settings{
		Name: "anthropic-" + suffix, Window: time.Minute, BucketPeriod: time.Minute,
		MinSamples: 2, FailureRateThreshold: 0.5, CoolDown: cool,
	})
	oaiBr := mustBreaker(t, circuitbreaker.Settings{
		Name: "openai-" + suffix, MaxFailures: 2, CoolDown: cool,
	})
	shBr := mustBreaker(t, circuitbreaker.Settings{
		Name: "openaicompatible-" + suffix, MaxFailures: 2, CoolDown: cool,
	})

	return isolationFixture{
		cool: cool,
		anthFail: anthropic.New(anthropic.Config{
			APIKey: "k", BaseURL: failSrv.URL, MaxRetries: &zero, Breaker: anthBr,
		}, log, tr, nil),
		anthOK: anthropic.New(anthropic.Config{
			APIKey: "k", BaseURL: okSrv.URL, MaxRetries: &zero, Breaker: anthBr,
		}, log, tr, nil),
		oaiFail: openai.New(openai.Config{
			APIKey: "k", BaseURL: failSrv.URL + "/v1", MaxRetries: &zero, Breaker: oaiBr,
		}, log, tr, nil),
		oaiOK: openai.New(openai.Config{
			APIKey: "k", BaseURL: okSrv.URL + "/v1", MaxRetries: &zero, Breaker: oaiBr,
		}, log, tr, nil),
		shFail: openaicompatible.New(openaicompatible.Config{
			ProviderName: openaicompatible.ProviderNameSelfHosted,
			APIKey:       "", BaseURL: failSrv.URL + "/v1", MaxRetries: &zero,
			AuthMode: openaicompatible.AuthBearerOmitEmpty, ExtraModels: []string{"local-m"},
			Breaker: shBr,
		}, log, tr, nil),
		shOK: openaicompatible.New(openaicompatible.Config{
			ProviderName: openaicompatible.ProviderNameSelfHosted,
			APIKey:       "", BaseURL: okSrv.URL + "/v1", MaxRetries: &zero,
			AuthMode: openaicompatible.AuthBearerOmitEmpty, ExtraModels: []string{"local-m"},
			Breaker: shBr,
		}, log, tr, nil),
		anthReq: provider.Request{
			Model: "claude-sonnet-4-5", Messages: []provider.Message{{Role: "user", Content: "hi"}},
		},
		oaiReq: provider.Request{
			Model: "gpt-4o", Messages: []provider.Message{{Role: "user", Content: "hi"}},
		},
		shReq: provider.Request{
			Model: "local-m", Messages: []provider.Message{{Role: "user", Content: "hi"}},
		},
	}
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

func tripProviderBreaker(t *testing.T, p provider.Provider, req provider.Request, cool time.Duration, failures int) {
	t.Helper()
	for i := 0; i < failures; i++ {
		_, _ = p.Complete(context.Background(), req)
	}
	_, err := p.Complete(context.Background(), req)
	var pe *provider.ProviderError
	if !errors.As(err, &pe) {
		t.Fatalf("%s want circuit_open, got %v", p.Name(), err)
	}
	if pe.Reason != provider.ErrorReasonCircuitOpen {
		t.Fatalf("%s Reason=%q", p.Name(), pe.Reason)
	}
	if pe.RetryAfter != cool {
		t.Fatalf("%s RetryAfter=%v", p.Name(), pe.RetryAfter)
	}
}

func assertCompleteOK(t *testing.T, p provider.Provider, req provider.Request) {
	t.Helper()
	resp, err := p.Complete(context.Background(), req)
	if err != nil {
		t.Fatalf("%s affected by foreign breaker: %v", p.Name(), err)
	}
	_ = resp.Body.Close()
}
