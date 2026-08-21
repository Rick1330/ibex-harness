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
		if err := registerProviderModels(catalog, p, byModel, caps); err != nil {
			return nil, err
		}
	}
	return &Registry{providers: byModel, capabilities: caps}, nil
}

func registerProviderModels(
	catalog CapabilityCatalog,
	p Provider,
	byModel map[string]Provider,
	caps map[string]ModelCapability,
) error {
	for _, model := range p.SupportedModels() {
		if existing, ok := byModel[model]; ok {
			return fmt.Errorf("%w: %q claimed by %q and %q",
				ErrDuplicateModel, model, existing.Name(), p.Name())
		}
		cap, err := lookupValidatedCapability(catalog, model, p.Name())
		if err != nil {
			return err
		}
		byModel[model] = p
		caps[model] = cap
	}
	return nil
}

func lookupValidatedCapability(catalog CapabilityCatalog, model, providerName string) (ModelCapability, error) {
	cap, ok := catalog.Lookup(model)
	if !ok {
		return ModelCapability{}, fmt.Errorf("%w: %q (provider %q)", ErrMissingCapability, model, providerName)
	}
	if err := ValidateCapability(cap); err != nil {
		return ModelCapability{}, fmt.Errorf("model %q: %w", model, err)
	}
	if cap.ModelID != model {
		return ModelCapability{}, fmt.Errorf("%w: catalog key %q has ModelID %q", ErrInvalidCapability, model, cap.ModelID)
	}
	return cap, nil
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
