package provider

import (
	"errors"
	"fmt"
)

// ErrDuplicateModel is returned by NewRegistry when two providers claim the same model ID.
var ErrDuplicateModel = errors.New("provider model conflict")

// Registry maps model IDs to provider implementations and capability records.
// It is built once at service startup and is read-only thereafter.
type Registry struct {
	providers    map[string]Provider
	capabilities map[string]ModelCapability
}

// NewRegistry constructs a Registry from the given providers.
// catalog must supply a valid capability for every SupportedModels() ID.
// Returns ErrDuplicateModel when two providers claim the same model ID.
// Returns ErrMissingCapability when a model has no catalog entry.
// Returns ErrInvalidCapability when a catalog row fails validation or ModelID
// does not match the lookup key.
func NewRegistry(catalog CapabilityCatalog, providers ...Provider) (*Registry, error) {
	byModel := make(map[string]Provider)
	caps := make(map[string]ModelCapability)
	for _, p := range providers {
		for _, model := range p.SupportedModels() {
			if existing, ok := byModel[model]; ok {
				return nil, fmt.Errorf("%w: %q claimed by %q and %q",
					ErrDuplicateModel, model, existing.Name(), p.Name())
			}
			cap, ok := catalog.Lookup(model)
			if !ok {
				return nil, fmt.Errorf("%w: %q (provider %q)", ErrMissingCapability, model, p.Name())
			}
			if err := ValidateCapability(cap); err != nil {
				return nil, fmt.Errorf("%w: model %q: %v", ErrInvalidCapability, model, err)
			}
			if cap.ModelID != model {
				return nil, fmt.Errorf("%w: catalog key %q has ModelID %q", ErrInvalidCapability, model, cap.ModelID)
			}
			byModel[model] = p
			caps[model] = cap
		}
	}
	return &Registry{providers: byModel, capabilities: caps}, nil
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

// Capability returns the capability record for the given model ID.
// Returns (ModelCapability{}, false) if no capability is registered.
// Callers must check ok; a zero ModelCapability is not a silent default.
func (r *Registry) Capability(model string) (ModelCapability, bool) {
	if r == nil {
		return ModelCapability{}, false
	}
	cap, ok := r.capabilities[model]
	return cap, ok
}
