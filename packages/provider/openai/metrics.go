package openai

// Metrics records upstream provider outcomes and retries.
type Metrics interface {
	IncProviderRequest(provider, statusClass string)
	IncProviderRetry(provider string)
}

type noopMetrics struct{}

func (noopMetrics) IncProviderRequest(string, string) {
	// No-op when no metrics registry is wired.
}

func (noopMetrics) IncProviderRetry(string) {
	// No-op when no metrics registry is wired.
}
