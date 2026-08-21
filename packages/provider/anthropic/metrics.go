package anthropic

// Metrics records upstream provider outcomes and retries.
type Metrics interface {
	IncProviderRequest(provider, statusClass string)
	IncProviderRetry(provider string)
}

type noopMetrics struct{}

func (noopMetrics) IncProviderRequest(string, string) {
	_ = struct{}{}
}

func (noopMetrics) IncProviderRetry(string) {
	_ = struct{}{}
}
