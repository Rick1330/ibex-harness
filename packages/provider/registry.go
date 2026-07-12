package provider

import "fmt"

// Registry maps model IDs to provider implementations.
// It is built once at service startup and is read-only thereafter.
type Registry struct {
	providers map[string]Provider
}

// NewRegistry constructs a Registry from the given providers.
// Panics if two providers claim the same model ID.
func NewRegistry(providers ...Provider) *Registry {
	byModel := make(map[string]Provider)
	for _, p := range providers {
		for _, model := range p.SupportedModels() {
			if existing, ok := byModel[model]; ok {
				panic(fmt.Sprintf("provider model conflict: %q claimed by %q and %q",
					model, existing.Name(), p.Name()))
			}
			byModel[model] = p
		}
	}
	return &Registry{providers: byModel}
}

// For returns the provider for the given model ID.
// Returns (nil, ErrNoProviderForModel) if no provider supports the model.
func (r *Registry) For(model string) (Provider, error) {
	if r == nil {
		return nil, ErrNoProviderForModel
	}
	p, ok := r.providers[model]
	if !ok {
		return nil, ErrNoProviderForModel
	}
	return p, nil
}
