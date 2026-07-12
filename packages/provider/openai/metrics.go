package openai

// Metrics records upstream provider outcomes and retries.
type Metrics interface {
	IncProviderRequest(provider, statusClass string)
	IncProviderRetry(provider string)
}

type noopMetrics struct{}

// IncProviderRequest is intentionally empty when no metrics registry is wired.
func (noopMetrics) IncProviderRequest(string, string) {}

// IncProviderRetry is intentionally empty when no metrics registry is wired.
func (noopMetrics) IncProviderRetry(string) {}
