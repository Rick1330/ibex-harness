package anthropic

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strings"

	"github.com/Rick1330/ibex-harness/packages/circuitbreaker"
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
	if c.cfg.Breaker == nil {
		return c.completeOnce(ctx, req)
	}
	out, err := c.cfg.Breaker.Execute(func() (any, error) {
		return c.completeUnderBreaker(ctx, req)
	})
	return decodeBreakerResult(c.Name(), out, err)
}

func (c *Client) completeUnderBreaker(ctx context.Context, req provider.Request) (any, error) {
	resp, err := c.completeOnce(ctx, req)
	if err != nil {
		return nil, classifyForBreaker(ctx, err)
	}
	return resp, nil
}

func (c *Client) completeOnce(ctx context.Context, req provider.Request) (provider.Response, error) {
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

	base := c.cfg.BaseURL
	if strings.TrimSpace(req.BaseURLOverride) != "" {
		base = strings.TrimSpace(req.BaseURLOverride)
	}
	return c.executeWithRetry(ctx, span, upstreamCall{
		URL:            provider.JoinBaseURL(base, "/v1/messages"),
		Body:           body,
		Stream:         req.Stream,
		Model:          req.Model,
		APIKeyOverride: req.APIKeyOverride,
	})
}

// classifyForBreaker keeps caller abandonment from tripping the breaker, while
// ensuring upstream timeouts that wrap DeadlineExceeded still count as failures.
func classifyForBreaker(ctx context.Context, err error) error {
	switch {
	case errors.Is(ctx.Err(), context.Canceled):
		return context.Canceled
	case errors.Is(ctx.Err(), context.DeadlineExceeded):
		return context.DeadlineExceeded
	case errors.Is(err, context.DeadlineExceeded):
		return fmt.Errorf("upstream timed out: %v", err)
	default:
		return err
	}
}

func decodeBreakerResult(name string, out any, err error) (provider.Response, error) {
	if err != nil {
		return mapBreakerError(name, err)
	}
	resp, ok := out.(provider.Response)
	if !ok {
		return provider.Response{}, fmt.Errorf("%s: circuit breaker returned unexpected result", name)
	}
	return resp, nil
}

func mapBreakerError(name string, err error) (provider.Response, error) {
	var pe *provider.ProviderError
	if errors.As(err, &pe) {
		return provider.Response{}, pe
	}
	if errors.Is(err, circuitbreaker.ErrOpen) {
		out := &provider.ProviderError{
			ProviderName:   name,
			StatusCode:     http.StatusServiceUnavailable,
			ProviderErrMsg: "circuit breaker open",
			Reason:         provider.ErrorReasonCircuitOpen,
		}
		var oe *circuitbreaker.OpenError
		if errors.As(err, &oe) && oe != nil {
			out.RetryAfter = oe.RetryAfter
		}
		return provider.Response{}, out
	}
	return provider.Response{}, err
}

func (c *Client) doRequest(ctx context.Context, call upstreamCall) (*http.Response, error) {
	return provider.DoUpstream(
		ctx,
		c.cfg.StreamTimeout,
		c.clients.Sync,
		c.clients.Stream,
		c.newMessagesRequest,
		provider.UpstreamCall{
			URL: call.URL, Body: call.Body, Stream: call.Stream,
			APIKeyOverride: call.APIKeyOverride,
		},
	)
}

func (c *Client) newMessagesRequest(ctx context.Context, call provider.UpstreamCall) (*http.Request, error) {
	key := call.APIKeyOverride
	if key == "" {
		key = c.cfg.APIKey
	}
	return provider.NewJSONPostRequest(ctx, call, map[string]string{
		"Content-Type":      "application/json",
		"x-api-key":         key,
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
