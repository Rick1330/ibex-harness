package main

import (
	"fmt"
	"strings"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/provider/openai"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	"go.opentelemetry.io/otel/trace"
)

func buildProviderRegistry(cfg config.Config, log *logger.Logger, tracer trace.Tracer, reg *metrics.ProxyRegistry) (*provider.Registry, error) {
	if strings.EqualFold(strings.TrimSpace(cfg.LLMMode), "mock") {
		return provider.NewRegistry()
	}
	maxRetries := cfg.OpenAI.MaxRetries
	client := openai.New(openai.Config{
		APIKey:         cfg.OpenAI.APIKey,
		BaseURL:        cfg.OpenAI.BaseURL,
		Timeout:        cfg.OpenAI.RequestTimeout,
		MaxRetries:     &maxRetries,
		RetryBaseDelay: cfg.OpenAI.RetryBaseDelay,
	}, log, tracer, reg)
	out, err := provider.NewRegistry(client)
	if err != nil {
		return nil, fmt.Errorf("provider registry: %w", err)
	}
	return out, nil
}
