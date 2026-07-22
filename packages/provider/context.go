package provider

import "context"

type providerKey struct{}

// WithProvider attaches the selected LLM provider to ctx.
// Routing middleware selects a provider once so downstream handlers stay
// registry-independent and only consume the attached value.
func WithProvider(ctx context.Context, p Provider) context.Context {
	return context.WithValue(ctx, providerKey{}, p)
}

// ProviderFromContext returns the provider attached by routing middleware.
// ok is false when no provider is present — valid outside the routed chain
// (tests, non-chat paths) and must be handled by callers that require one.
func ProviderFromContext(ctx context.Context) (Provider, bool) {
	p, ok := ctx.Value(providerKey{}).(Provider)
	return p, ok && p != nil
}
