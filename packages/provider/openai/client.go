package openai

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"go.opentelemetry.io/otel/trace"
)

// Client implements provider.Provider for the OpenAI API.
type Client struct {
	cfg          Config
	httpClient   *http.Client
	streamClient *http.Client
	log          *logger.Logger
	tracer       trace.Tracer
	metrics      Metrics
}

// New constructs an OpenAI Client with a shared http.Client for connection pooling.
func New(cfg Config, log *logger.Logger, tracer trace.Tracer, metrics Metrics) *Client {
	cfg.ApplyDefaults()
	if metrics == nil {
		metrics = noopMetrics{}
	}
	clients := provider.NewHTTPClients(cfg.Timeout)
	return &Client{
		cfg:          cfg,
		httpClient:   clients.Sync,
		streamClient: clients.Stream,
		log:          log,
		tracer:       provider.TracerOrNoop(tracer, "openai"),
		metrics:      metrics,
	}
}

func (c *Client) Name() string { return "openai" }

const (
	modelGPT4o      = "gpt-4o"
	modelGPT4oMini  = "gpt-4o-mini"
	modelGPT4Turbo  = "gpt-4-turbo"
	modelGPT35Turbo = "gpt-3.5-turbo"
)

func builtInSupportedModels() []string {
	return []string{modelGPT4o, modelGPT4oMini, modelGPT4Turbo, modelGPT35Turbo}
}

// SupportedModels returns the allowlist checked before upstream requests so
// unknown model IDs fail closed as PROVIDER_NOT_CONFIGURED instead of leaking
// arbitrary model strings to the provider.
func (c *Client) SupportedModels() []string {
	return provider.MergeSupportedModels(builtInSupportedModels(), c.cfg.ExtraModels)
}

// Complete sends a chat completion request to OpenAI.
// When req.Stream is true, Body is a live SSE stream (caller must close it).
func (c *Client) Complete(ctx context.Context, req provider.Request) (provider.Response, error) {
	ctx, span := provider.StartCompleteSpan(ctx, c.tracer, provider.CompleteSpan{
		Names: provider.CompleteSpanNames{Span: "openai.Complete", Provider: c.Name()},
		Req:   req,
	})
	defer span.End()

	body, err := c.marshalRequest(req)
	if err != nil {
		provider.RecordSpanErr(span, err)
		return provider.Response{}, err
	}

	return c.executeWithRetry(ctx, span, upstreamCall{
		URL:    provider.JoinBaseURL(c.cfg.BaseURL, "/chat/completions"),
		Body:   body,
		Stream: req.Stream,
	})
}

func (c *Client) marshalRequest(req provider.Request) ([]byte, error) {
	body, err := marshalOpenAIRequestBody(req)
	if err != nil {
		return nil, fmt.Errorf("openai request: %w", err)
	}
	return body, nil
}

func (c *Client) doRequest(ctx context.Context, call upstreamCall) (*http.Response, error) {
	return provider.DoUpstream(
		ctx,
		c.cfg.StreamTimeout,
		c.httpClient,
		c.streamClient,
		c.newChatRequest,
		provider.UpstreamCall{URL: call.URL, Body: call.Body, Stream: call.Stream},
	)
}

func (c *Client) newChatRequest(ctx context.Context, call provider.UpstreamCall) (*http.Request, error) {
	return provider.NewJSONPostRequest(ctx, call, map[string]string{
		"Content-Type":  "application/json",
		"Authorization": "Bearer " + c.cfg.APIKey,
	})
}

func readProviderError(name string, resp *http.Response) *provider.ProviderError {
	return provider.ReadProviderError(name, resp, extractOpenAIErrorMessage)
}

func extractOpenAIErrorMessage(raw []byte) string {
	var payload struct {
		Error struct {
			Message string `json:"message"`
		} `json:"error"`
	}
	if err := json.Unmarshal(raw, &payload); err != nil || payload.Error.Message == "" {
		return "upstream provider error"
	}
	return payload.Error.Message
}

func isRetryableStatus(code int) bool {
	return provider.IsRetryableHTTPStatus(code)
}

func (c *Client) waitBeforeRetry(ctx context.Context, attempt int, lastErr error) error {
	lastErr = enrichOpenAIRetryAfter(lastErr)
	return provider.WaitBeforeRetry(ctx, c.cfg.RetryBaseDelay, attempt, lastErr)
}

func enrichOpenAIRetryAfter(lastErr error) error {
	pe, ok := lastErr.(*provider.ProviderError)
	if !ok {
		return lastErr
	}
	if pe.StatusCode != http.StatusTooManyRequests {
		return lastErr
	}
	if pe.RetryAfter > 0 {
		return lastErr
	}
	ra := retryAfterFromProvider(pe)
	if ra <= 0 {
		return lastErr
	}
	copied := *pe
	copied.RetryAfter = ra
	return &copied
}

func retryAfterFromProvider(pe *provider.ProviderError) time.Duration {
	var payload struct {
		Error struct {
			RetryAfter float64 `json:"retry_after"`
		} `json:"error"`
	}
	if err := json.Unmarshal(pe.ProviderBody, &payload); err == nil && payload.Error.RetryAfter > 0 {
		return time.Duration(payload.Error.RetryAfter * float64(time.Second))
	}
	return 0
}

// RetryAfterHeader parses the Retry-After response header when present.
// Deprecated: prefer provider.RetryAfterHeader; kept for existing package tests.
func RetryAfterHeader(hdr string) time.Duration {
	return provider.RetryAfterHeader(hdr)
}
