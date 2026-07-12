package provider

import (
	"errors"
	"fmt"
)

// ErrDuplicateModel is returned by NewRegistry when two providers claim the same model ID.
var ErrDuplicateModel = errors.New("provider model conflict")

// Registry maps model IDs to provider implementations.
// It is built once at service startup and is read-only thereafter.
type Registry struct {
	providers map[string]Provider
}

// NewRegistry constructs a Registry from the given providers.
// Returns ErrDuplicateModel when two providers claim the same model ID.
func NewRegistry(providers ...Provider) (*Registry, error) {
	byModel := make(map[string]Provider)
	for _, p := range providers {
		for _, model := range p.SupportedModels() {
			if existing, ok := byModel[model]; ok {
				return nil, fmt.Errorf("%w: %q claimed by %q and %q",
					ErrDuplicateModel, model, existing.Name(), p.Name())
			}
			byModel[model] = p
		}
	}
	return &Registry{providers: byModel}, nil
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
