package openai

import (
	"context"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/provider/openaicompatible"
	"go.opentelemetry.io/otel/trace"
)

// Client implements provider.Provider for the hosted OpenAI API.
// It wraps the shared OpenAI-compatible client with curated built-ins.
type Client struct {
	inner *openaicompatible.Client
}

// New constructs an OpenAI Client with a shared http.Client for connection pooling.
func New(cfg Config, log *logger.Logger, tracer trace.Tracer, metrics Metrics) *Client {
	cfg.ApplyDefaults()
	var m openaicompatible.Metrics
	if metrics != nil {
		m = metrics
	}
	inner := openaicompatible.New(openaicompatible.Config{
		ProviderName:   openaicompatible.ProviderNameOpenAI,
		APIKey:         cfg.APIKey,
		BaseURL:        cfg.BaseURL,
		Timeout:        cfg.Timeout,
		StreamTimeout:  cfg.StreamTimeout,
		MaxRetries:     cfg.MaxRetries,
		RetryBaseDelay: cfg.RetryBaseDelay,
		BuiltInModels:  builtInSupportedModels(),
		ExtraModels:    cfg.ExtraModels,
		AuthMode:       openaicompatible.AuthBearerAlways,
	}, log, tracer, m)
	return &Client{inner: inner}
}

func (c *Client) Name() string { return c.inner.Name() }

func (c *Client) SupportedModels() []string { return c.inner.SupportedModels() }

// Complete sends a chat completion request to OpenAI.
func (c *Client) Complete(ctx context.Context, req provider.Request) (provider.Response, error) {
	return c.inner.Complete(ctx, req)
}

const (
	modelGPT4o      = "gpt-4o"
	modelGPT4oMini  = "gpt-4o-mini"
	modelGPT4Turbo  = "gpt-4-turbo"
	modelGPT35Turbo = "gpt-3.5-turbo"
)

func builtInSupportedModels() []string {
	return []string{modelGPT4o, modelGPT4oMini, modelGPT4Turbo, modelGPT35Turbo}
}

// RetryAfterHeader parses the Retry-After response header when present.
// Deprecated: prefer provider.RetryAfterHeader; kept for existing package tests.
func RetryAfterHeader(hdr string) time.Duration {
	return provider.RetryAfterHeader(hdr)
}

// StreamAccumulator is an alias for the shared OpenAI-compatible SSE accumulator.
type StreamAccumulator = openaicompatible.StreamAccumulator

// NewStreamAccumulator constructs an empty accumulator.
func NewStreamAccumulator() *StreamAccumulator {
	return openaicompatible.NewStreamAccumulator()
}

// MaxAccumulatedContentBytes is the soft cap for accumulated completion text (ADR-0027).
const MaxAccumulatedContentBytes = openaicompatible.MaxAccumulatedContentBytes
