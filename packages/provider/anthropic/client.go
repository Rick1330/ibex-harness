package anthropic

import (
	"context"
	"encoding/json"
	"net/http"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"go.opentelemetry.io/otel/trace"
)

// Client implements provider.Provider for the Anthropic Messages API.
// Responses are translated to OpenAI-compatible JSON/SSE (ADR-0040).
type Client struct {
	cfg     Config
	clients provider.HTTPClients
	log     *logger.Logger
	tracer  trace.Tracer
	metrics Metrics
}

// New constructs an Anthropic Client with a shared http.Client for connection pooling.
func New(cfg Config, log *logger.Logger, tracer trace.Tracer, metrics Metrics) *Client {
	cfg.ApplyDefaults()
	if metrics == nil {
		metrics = noopMetrics{}
	}
	return &Client{
		cfg:     cfg,
		clients: provider.NewHTTPClients(cfg.Timeout),
		log:     log,
		tracer:  provider.TracerOrNoop(tracer, "anthropic"),
		metrics: metrics,
	}
}

func (c *Client) Name() string { return "anthropic" }

const (
	modelClaudeSonnet45 = "claude-sonnet-4-5"
	modelClaudeHaiku45  = "claude-haiku-4-5"
	modelClaudeOpus45   = "claude-opus-4-5"
)

func builtInSupportedModels() []string {
	return []string{modelClaudeSonnet45, modelClaudeHaiku45, modelClaudeOpus45}
}

// SupportedModels returns the allowlist checked before upstream requests.
func (c *Client) SupportedModels() []string {
	return provider.MergeSupportedModels(builtInSupportedModels(), c.cfg.ExtraModels)
}

// Complete sends a Messages API request and returns an OpenAI-compatible body.
func (c *Client) Complete(ctx context.Context, req provider.Request) (provider.Response, error) {
	ctx, span := provider.StartCompleteSpan(ctx, c.tracer, provider.CompleteSpan{
		Names: provider.CompleteSpanNames{Span: "anthropic.Complete", Provider: c.Name()},
		Req:   req,
	})
	defer span.End()

	body, err := marshalAnthropicRequestBody(req, c.cfg.DefaultTokens)
	if err != nil {
		provider.RecordSpanErr(span, err)
		return provider.Response{}, err
	}

	return c.executeWithRetry(ctx, span, upstreamCall{
		URL:    provider.JoinBaseURL(c.cfg.BaseURL, "/v1/messages"),
		Body:   body,
		Stream: req.Stream,
		Model:  req.Model,
	})
}

func (c *Client) doRequest(ctx context.Context, call upstreamCall) (*http.Response, error) {
	return provider.DoUpstream(
		ctx,
		c.cfg.StreamTimeout,
		c.clients.Sync,
		c.clients.Stream,
		c.newMessagesRequest,
		provider.UpstreamCall{URL: call.URL, Body: call.Body, Stream: call.Stream},
	)
}

func (c *Client) newMessagesRequest(ctx context.Context, call provider.UpstreamCall) (*http.Request, error) {
	return provider.NewJSONPostRequest(ctx, call, map[string]string{
		"Content-Type":      "application/json",
		"x-api-key":         c.cfg.APIKey,
		"anthropic-version": c.cfg.APIVersion,
	})
}

func readProviderError(name string, resp *http.Response) *provider.ProviderError {
	return provider.ReadProviderError(name, resp, extractAnthropicErrorMessage)
}

func extractAnthropicErrorMessage(raw []byte) string {
	var payload struct {
		Error struct {
			Type    string `json:"type"`
			Message string `json:"message"`
		} `json:"error"`
		Type    string `json:"type"`
		Message string `json:"message"`
	}
	if err := json.Unmarshal(raw, &payload); err != nil {
		return "upstream provider error"
	}
	if payload.Error.Message != "" {
		return truncateErrMsg(payload.Error.Message)
	}
	if payload.Message != "" {
		return truncateErrMsg(payload.Message)
	}
	return "upstream provider error"
}

func isRetryableStatus(code int) bool {
	return provider.IsRetryableHTTPStatus(code, statusOverloaded)
}
