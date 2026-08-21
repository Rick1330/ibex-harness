package openaicompatible

// Metrics records upstream provider outcomes, retries, and per-attempt latency.
type Metrics interface {
	IncProviderRequest(provider, statusClass string)
	IncProviderRetry(provider string)
	ObserveProviderDurationSeconds(provider string, seconds float64)
}

type noopMetrics struct{}

func (noopMetrics) IncProviderRequest(string, string) { _ = 0 }

func (noopMetrics) IncProviderRetry(string) { _ = 0 }

func (noopMetrics) ObserveProviderDurationSeconds(string, float64) { _ = 0 }
