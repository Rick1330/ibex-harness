package bootstrap

import (
	"fmt"
	"strings"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/provider/anthropic"
	"github.com/Rick1330/ibex-harness/packages/provider/mockllm"
	"github.com/Rick1330/ibex-harness/packages/provider/openai"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	"go.opentelemetry.io/otel/trace"
)

func buildProviderRegistry(cfg config.Config, log *logger.Logger, tracer trace.Tracer, reg *metrics.ProxyRegistry) (*provider.Registry, error) {
	if strings.EqualFold(strings.TrimSpace(cfg.LLMMode), "mock") {
		return buildMockProviderRegistry(cfg)
	}
	return buildLiveProviderRegistry(cfg, log, tracer, reg)
}

// capabilityCatalog merges built-ins with overlays. Overlays may only cover
// ExtraModels IDs and must not clobber built-in curated rows (fail-closed).
func capabilityCatalog(cfg config.Config) (provider.CapabilityCatalog, error) {
	builtin := provider.BuiltInCapabilityCatalog()
	extraIDs := mergeExtraModelIDs(cfg)
	if err := validateCapabilityOverlays(builtin, extraIDs, cfg.ModelCapabilityOverlays); err != nil {
		return nil, err
	}
	overlay := provider.CatalogFromCapabilities(cfg.ModelCapabilityOverlays...)
	return provider.MergeCapabilityCatalog(builtin, overlay), nil
}

func mergeExtraModelIDs(cfg config.Config) []string {
	return provider.MergeSupportedModels(cfg.OpenAI.ExtraModels, cfg.Anthropic.ExtraModels)
}

func validateCapabilityOverlays(builtin provider.CapabilityCatalog, extraIDs []string, overlays []provider.ModelCapability) error {
	extraSet := make(map[string]struct{}, len(extraIDs))
	for _, id := range extraIDs {
		extraSet[id] = struct{}{}
	}
	for _, overlay := range overlays {
		id := strings.TrimSpace(overlay.ModelID)
		if _, ok := builtin.Lookup(id); ok {
			return fmt.Errorf("IBEX_MODEL_CAPABILITY_OVERLAYS: cannot override built-in model %q", id)
		}
		if _, ok := extraSet[id]; !ok {
			return fmt.Errorf("IBEX_MODEL_CAPABILITY_OVERLAYS: model %q is not listed in IBEX_LLM_EXTRA_MODELS or ANTHROPIC_EXTRA_MODELS", id)
		}
	}
	covered := make(map[string]struct{}, len(overlays))
	for _, overlay := range overlays {
		covered[strings.TrimSpace(overlay.ModelID)] = struct{}{}
	}
	for _, id := range extraIDs {
		if _, ok := builtin.Lookup(id); ok {
			continue
		}
		if _, ok := covered[id]; !ok {
			return fmt.Errorf("IBEX_MODEL_CAPABILITY_OVERLAYS: missing capability overlay for ExtraModels id %q", id)
		}
	}
	return nil
}

func buildMockProviderRegistry(cfg config.Config) (*provider.Registry, error) {
	// Defense in depth: Validate() also rejects this; keep fail-closed at wire-up.
	if strings.EqualFold(strings.TrimSpace(cfg.Environment), "production") {
		return nil, fmt.Errorf("IBEX_LLM_MODE=mock is not allowed when IBEX_ENV=production")
	}
	catalog, err := capabilityCatalog(cfg)
	if err != nil {
		return nil, fmt.Errorf("mock provider registry: %w", err)
	}
	out, err := provider.NewRegistry(catalog, mockllm.Provider{})
	if err != nil {
		return nil, fmt.Errorf("mock provider registry: %w", err)
	}
	return out, nil
}

func buildLiveProviderRegistry(cfg config.Config, log *logger.Logger, tracer trace.Tracer, reg *metrics.ProxyRegistry) (*provider.Registry, error) {
	var providers []provider.Provider

	if key := strings.TrimSpace(cfg.OpenAI.APIKey); key != "" {
		maxRetries := cfg.OpenAI.MaxRetries
		providers = append(providers, openai.New(openai.Config{
			APIKey:         key,
			BaseURL:        cfg.OpenAI.BaseURL,
			Timeout:        cfg.OpenAI.RequestTimeout,
			MaxRetries:     &maxRetries,
			RetryBaseDelay: cfg.OpenAI.RetryBaseDelay,
			ExtraModels:    cfg.OpenAI.ExtraModels,
		}, log, tracer, reg))
	}

	if key := strings.TrimSpace(cfg.Anthropic.APIKey); key != "" {
		maxRetries := cfg.Anthropic.MaxRetries
		providers = append(providers, anthropic.New(anthropic.Config{
			APIKey:         key,
			BaseURL:        cfg.Anthropic.BaseURL,
			Timeout:        cfg.Anthropic.RequestTimeout,
			MaxRetries:     &maxRetries,
			RetryBaseDelay: cfg.Anthropic.RetryBaseDelay,
			ExtraModels:    cfg.Anthropic.ExtraModels,
		}, log, tracer, reg))
	}

	if len(providers) == 0 {
		return nil, fmt.Errorf("live mode requires OPENAI_API_KEY and/or ANTHROPIC_API_KEY")
	}

	catalog, err := capabilityCatalog(cfg)
	if err != nil {
		return nil, fmt.Errorf("provider registry: %w", err)
	}
	out, err := provider.NewRegistry(catalog, providers...)
	if err != nil {
		return nil, fmt.Errorf("provider registry: %w", err)
	}
	return out, nil
}
