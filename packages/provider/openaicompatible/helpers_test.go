package openaicompatible

import (
	"sync/atomic"
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
