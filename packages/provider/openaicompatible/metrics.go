package openaicompatible

// Metrics records upstream provider outcomes and retries.
type Metrics interface {
	IncProviderRequest(provider, statusClass string)
	IncProviderRetry(provider string)
}

type noopMetrics struct{}

func (noopMetrics) IncProviderRequest(string, string) { _ = 0 }

func (noopMetrics) IncProviderRetry(string) { _ = 0 }
