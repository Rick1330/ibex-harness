package provider

import "context"

type providerKey struct{}

// WithProvider attaches the selected LLM provider to ctx.
func WithProvider(ctx context.Context, p Provider) context.Context {
	return context.WithValue(ctx, providerKey{}, p)
}

// ProviderFromContext returns the provider attached by routing middleware.
func ProviderFromContext(ctx context.Context) (Provider, bool) {
	p, ok := ctx.Value(providerKey{}).(Provider)
	return p, ok && p != nil
}

// MustProviderFromContext returns the provider or panics if missing.
// Handlers behind ProviderRoutingMiddleware must use this.
func MustProviderFromContext(ctx context.Context) Provider {
	p, ok := ProviderFromContext(ctx)
	if !ok {
		panic("provider: Provider missing from context; ProviderRoutingMiddleware required")
	}
	return p
}
