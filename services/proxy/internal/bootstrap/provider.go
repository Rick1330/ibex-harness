package bootstrap

import (
	"context"
	"fmt"
	"strings"

	"github.com/Rick1330/ibex-harness/packages/circuitbreaker"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/provider/anthropic"
	"github.com/Rick1330/ibex-harness/packages/provider/mockllm"
	"github.com/Rick1330/ibex-harness/packages/provider/openai"
	"github.com/Rick1330/ibex-harness/packages/provider/openaicompatible"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	"go.opentelemetry.io/otel/trace"
)

func buildProviderRegistry(cfg config.Config, log *logger.Logger, tracer trace.Tracer, reg *metrics.ProxyRegistry) (*provider.Registry, error) {
	if strings.EqualFold(strings.TrimSpace(cfg.LLMMode), "mock") {
		return buildMockProviderRegistry(cfg)
	}
	return buildLiveProviderRegistry(cfg, log, tracer, reg)
}

// capabilityCatalog merges built-ins with overlays. In mock mode ExtraModels and
// overlays are ignored (mockllm uses a fixed allowlist). In live mode overlays
// may only cover ExtraModels IDs that will actually be registered and must not
// clobber built-in curated rows (fail-closed).
func capabilityCatalog(cfg config.Config) (provider.CapabilityCatalog, error) {
	builtin := provider.BuiltInCapabilityCatalog()
	if isMockLLMMode(cfg) {
		return builtin, nil
	}
	extraByProvider, err := activeExtraModels(cfg)
	if err != nil {
		return nil, err
	}
	if err := validateCapabilityOverlays(builtin, extraByProvider, cfg.ModelCapabilityOverlays); err != nil {
		return nil, err
	}
	overlay := provider.CatalogFromCapabilities(cfg.ModelCapabilityOverlays...)
	return provider.MergeCapabilityCatalog(builtin, overlay), nil
}

func isMockLLMMode(cfg config.Config) bool {
	return strings.EqualFold(strings.TrimSpace(cfg.LLMMode), "mock")
}

// activeExtraModels returns ExtraModels that will be registered, keyed by the
// vendor provider string expected on overlay rows.
// Live mode rejects ExtraModels for a vendor when that vendor's API key is unset.
func activeExtraModels(cfg config.Config) (map[string]string, error) {
	out := make(map[string]string)
	if err := collectVendorExtras(out, vendorExtras{
		providerName: provider.CapabilityProviderOpenAI,
		apiKey:       cfg.OpenAI.APIKey,
		extras:       cfg.OpenAI.ExtraModels,
		keyEnv:       "OPENAI_API_KEY",
		extrasEnv:    "IBEX_LLM_EXTRA_MODELS",
	}); err != nil {
		return nil, err
	}
	if err := collectVendorExtras(out, vendorExtras{
		providerName: provider.CapabilityProviderAnthropic,
		apiKey:       cfg.Anthropic.APIKey,
		extras:       cfg.Anthropic.ExtraModels,
		keyEnv:       "ANTHROPIC_API_KEY",
		extrasEnv:    "ANTHROPIC_EXTRA_MODELS",
	}); err != nil {
		return nil, err
	}
	if err := collectSelfHostedExtras(out, cfg.SelfHosted); err != nil {
		return nil, err
	}
	return out, nil
}

func collectSelfHostedExtras(dst map[string]string, sh config.SelfHostedConfig) error {
	if !sh.Enabled {
		return nil
	}
	// Overlay vendor family stays "openai" (wire dialect); registry provider name is openaicompatible.
	return addVendorExtraIDs(dst, provider.CapabilityProviderOpenAI, sh.Models)
}

type vendorExtras struct {
	providerName string
	apiKey       string
	extras       []string
	keyEnv       string
	extrasEnv    string
}

func collectVendorExtras(dst map[string]string, in vendorExtras) error {
	if strings.TrimSpace(in.apiKey) == "" {
		return extrasRequireAPIKey(in)
	}
	return addVendorExtraIDs(dst, in.providerName, in.extras)
}

func extrasRequireAPIKey(in vendorExtras) error {
	if len(in.extras) == 0 {
		return nil
	}
	return fmt.Errorf("%s requires %s (or clear ExtraModels)", in.extrasEnv, in.keyEnv)
}

func addVendorExtraIDs(dst map[string]string, providerName string, extras []string) error {
	for _, raw := range extras {
		id := strings.TrimSpace(raw)
		if id == "" {
			continue
		}
		if prev, ok := dst[id]; ok && prev != providerName {
			return fmt.Errorf("ExtraModels id %q claimed by both %q and %q", id, prev, providerName)
		}
		dst[id] = providerName
	}
	return nil
}

func validateCapabilityOverlays(builtin provider.CapabilityCatalog, extraByProvider map[string]string, overlays []provider.ModelCapability) error {
	if err := rejectInvalidOverlays(builtin, extraByProvider, overlays); err != nil {
		return err
	}
	return requireExtraOverlays(builtin, extraByProvider, overlays)
}

func rejectInvalidOverlays(builtin provider.CapabilityCatalog, extraByProvider map[string]string, overlays []provider.ModelCapability) error {
	for _, overlay := range overlays {
		id := strings.TrimSpace(overlay.ModelID)
		if _, ok := builtin.Lookup(id); ok {
			return fmt.Errorf("IBEX_MODEL_CAPABILITY_OVERLAYS: cannot override built-in model %q", id)
		}
		wantProvider, ok := extraByProvider[id]
		if !ok {
			return fmt.Errorf("IBEX_MODEL_CAPABILITY_OVERLAYS: model %q is not listed in ExtraModels for an active provider (IBEX_LLM_EXTRA_MODELS, ANTHROPIC_EXTRA_MODELS, or IBEX_SELFHOSTED_MODELS)", id)
		}
		gotProvider := strings.TrimSpace(overlay.Provider)
		if gotProvider != wantProvider {
			return fmt.Errorf("IBEX_MODEL_CAPABILITY_OVERLAYS: model %q provider must be %q (got %q)", id, wantProvider, gotProvider)
		}
	}
	return nil
}

func requireExtraOverlays(builtin provider.CapabilityCatalog, extraByProvider map[string]string, overlays []provider.ModelCapability) error {
	covered := make(map[string]struct{}, len(overlays))
	for _, overlay := range overlays {
		covered[strings.TrimSpace(overlay.ModelID)] = struct{}{}
	}
	for id := range extraByProvider {
		if _, ok := builtin.Lookup(id); ok {
			continue
		}
		if _, ok := covered[id]; ok {
			continue
		}
		return fmt.Errorf("IBEX_MODEL_CAPABILITY_OVERLAYS: missing capability overlay for ExtraModels id %q", id)
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
	providers, err := collectLiveProviders(cfg, log, tracer, reg)
	if err != nil {
		return nil, err
	}
	if len(providers) == 0 {
		return nil, fmt.Errorf("live mode requires OPENAI_API_KEY, ANTHROPIC_API_KEY, and/or IBEX_SELFHOSTED_ENABLED")
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

func collectLiveProviders(cfg config.Config, log *logger.Logger, tracer trace.Tracer, reg *metrics.ProxyRegistry) ([]provider.Provider, error) {
	var providers []provider.Provider
	providers = appendLiveIfPresent(providers, strings.TrimSpace(cfg.OpenAI.APIKey) != "", func() provider.Provider {
		maxRetries := cfg.OpenAI.MaxRetries
		return openai.New(openai.Config{
			APIKey:         cfg.OpenAI.APIKey,
			BaseURL:        cfg.OpenAI.BaseURL,
			Timeout:        cfg.OpenAI.RequestTimeout,
			MaxRetries:     &maxRetries,
			RetryBaseDelay: cfg.OpenAI.RetryBaseDelay,
			ExtraModels:    cfg.OpenAI.ExtraModels,
		}, log, tracer, reg)
	})
	providers = appendLiveIfPresent(providers, strings.TrimSpace(cfg.Anthropic.APIKey) != "", func() provider.Provider {
		maxRetries := cfg.Anthropic.MaxRetries
		return anthropic.New(anthropic.Config{
			APIKey:         cfg.Anthropic.APIKey,
			BaseURL:        cfg.Anthropic.BaseURL,
			Timeout:        cfg.Anthropic.RequestTimeout,
			MaxRetries:     &maxRetries,
			RetryBaseDelay: cfg.Anthropic.RetryBaseDelay,
			ExtraModels:    cfg.Anthropic.ExtraModels,
		}, log, tracer, reg)
	})
	if !cfg.SelfHosted.Enabled {
		return providers, nil
	}
	p, err := newSelfHostedProvider(cfg, log, tracer, reg)
	if err != nil {
		return nil, err
	}
	return append(providers, p), nil
}

func appendLiveIfPresent(dst []provider.Provider, present bool, build func() provider.Provider) []provider.Provider {
	if !present {
		return dst
	}
	return append(dst, build())
}

func newSelfHostedProvider(
	cfg config.Config,
	log *logger.Logger,
	tracer trace.Tracer,
	reg *metrics.ProxyRegistry,
) (provider.Provider, error) {
	base := cfg.SelfHosted.NormalizeBaseURL()
	if err := waitSelfHostedReady(context.Background(), base, cfg.SelfHosted, log); err != nil {
		return nil, err
	}
	br := circuitbreaker.New(circuitbreaker.Settings{
		Name:        openaicompatible.ProviderNameSelfHosted,
		MaxFailures: cfg.SelfHosted.BreakerFailures,
		CoolDown:    cfg.SelfHosted.BreakerCoolDown,
	})
	maxRetries := cfg.OpenAI.MaxRetries
	return openaicompatible.New(openaicompatible.Config{
		ProviderName:   openaicompatible.ProviderNameSelfHosted,
		APIKey:         cfg.SelfHosted.APIKey,
		BaseURL:        base,
		Timeout:        cfg.OpenAI.RequestTimeout,
		MaxRetries:     &maxRetries,
		RetryBaseDelay: cfg.OpenAI.RetryBaseDelay,
		ExtraModels:    cfg.SelfHosted.Models,
		AuthMode:       openaicompatible.AuthBearerOmitEmpty,
		Breaker:        br,
	}, log, tracer, reg), nil
}
