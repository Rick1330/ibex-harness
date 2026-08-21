package openaicompatible

import (
	"context"
	"errors"
	"sync/atomic"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
)

type stubBreaker struct {
	err    error
	result any
}

func (s stubBreaker) Execute(fn func() (any, error)) (any, error) {
	if s.err != nil {
		return nil, s.err
	}
	if s.result != nil {
		return s.result, nil
	}
	return fn()
}

type countingMetrics struct {
	requests  atomic.Int32
	retries   atomic.Int32
	durations atomic.Int32
}

func (m *countingMetrics) IncProviderRequest(string, string) { m.requests.Add(1) }
func (m *countingMetrics) IncProviderRetry(string)           { m.retries.Add(1) }
func (m *countingMetrics) ObserveProviderDurationSeconds(string, float64) {
	m.durations.Add(1)
}

func zeroRetries() *int {
	v := 0
	return &v
}

func newSelfHostedTestClient(baseURL string, br Breaker) *Client {
	return New(Config{
		ProviderName: ProviderNameSelfHosted,
		BaseURL:      baseURL,
		MaxRetries:   zeroRetries(),
		AuthMode:     AuthBearerOmitEmpty,
		ExtraModels:  []string{"m"},
		Breaker:      br,
	}, logger.Discard("t"), telemetry.NoopTracer("t"), nil)
}

func completeHi(c *Client) (provider.Response, error) {
	return c.Complete(context.Background(), provider.Request{
		Model: "m", Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
}

func requireProviderReason(t *testing.T, err error, want string) {
	t.Helper()
	var pe *provider.ProviderError
	if !errors.As(err, &pe) {
		t.Fatalf("err=%v", err)
	}
	if pe.Reason != want {
		t.Fatalf("Reason=%q want %q", pe.Reason, want)
	}
}
