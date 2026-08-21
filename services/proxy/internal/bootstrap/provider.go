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

func buildMockProviderRegistry(cfg config.Config) (*provider.Registry, error) {
	// Defense in depth: Validate() also rejects this; keep fail-closed at wire-up.
	if strings.EqualFold(strings.TrimSpace(cfg.Environment), "production") {
		return nil, fmt.Errorf("IBEX_LLM_MODE=mock is not allowed when IBEX_ENV=production")
	}
	out, err := provider.NewRegistry(mockllm.Provider{})
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

	out, err := provider.NewRegistry(providers...)
	if err != nil {
		return nil, fmt.Errorf("provider registry: %w", err)
	}
	return out, nil
}
