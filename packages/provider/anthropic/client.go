package anthropic

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"strings"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"
	"go.opentelemetry.io/otel/trace/noop"
)

// Client implements provider.Provider for the Anthropic Messages API.
// Responses are translated to OpenAI-compatible JSON/SSE (ADR-0040).
type Client struct {
	cfg          Config
	httpClient   *http.Client
	streamClient *http.Client
	log          *logger.Logger
	tracer       trace.Tracer
	metrics      Metrics
}

// New constructs an Anthropic Client with a shared http.Client for connection pooling.
func New(cfg Config, log *logger.Logger, tracer trace.Tracer, metrics Metrics) *Client {
	cfg.ApplyDefaults()
	if metrics == nil {
		metrics = noopMetrics{}
	}
	if tracer == nil {
		tracer = noop.NewTracerProvider().Tracer("anthropic")
	}
	httpClient := provider.NewPooledHTTPClient(cfg.Timeout)
	return &Client{
		cfg:          cfg,
		httpClient:   httpClient,
		streamClient: provider.StreamHTTPClient(httpClient),
		log:          log,
		tracer:       tracer,
		metrics:      metrics,
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
	ctx, span := c.tracer.Start(ctx, "anthropic.Complete",
		trace.WithAttributes(
			attribute.String("provider.name", c.Name()),
			attribute.String("llm.model", req.Model),
			attribute.Bool("llm.stream", req.Stream),
		),
	)
	defer span.End()

	body, err := marshalAnthropicRequestBody(req, c.cfg.DefaultTokens)
	if err != nil {
		provider.RecordSpanErr(span, err)
		return provider.Response{}, err
	}

	url := strings.TrimRight(c.cfg.BaseURL, "/") + "/v1/messages"
	return c.executeWithRetry(ctx, span, upstreamCall{
		URL: url, Body: body, Stream: req.Stream, Model: req.Model,
	})
}

func (c *Client) doRequest(ctx context.Context, call upstreamCall) (*http.Response, error) {
	reqCtx, cancel := provider.StreamRequestContext(ctx, call.Stream, c.cfg.StreamTimeout)
	httpReq, err := c.newMessagesRequest(reqCtx, call)
	if err != nil {
		cancel()
		return nil, err
	}
	client := c.httpClient
	if call.Stream {
		client = c.streamClient
	}
	resp, err := client.Do(httpReq)
	if err != nil {
		cancel()
		return nil, err
	}
	return provider.AttachStreamCancel(resp, call.Stream, cancel), nil
}

func (c *Client) newMessagesRequest(ctx context.Context, call upstreamCall) (*http.Request, error) {
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, call.URL, bytes.NewReader(call.Body))
	if err != nil {
		return nil, err
	}
	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("x-api-key", c.cfg.APIKey)
	httpReq.Header.Set("anthropic-version", c.cfg.APIVersion)
	if call.Stream {
		httpReq.Header.Set("Accept", "text/event-stream")
	}
	return httpReq, nil
}

func readProviderError(name string, resp *http.Response) *provider.ProviderError {
	raw, _ := io.ReadAll(io.LimitReader(resp.Body, 64*1024))
	return &provider.ProviderError{
		ProviderName:   name,
		StatusCode:     resp.StatusCode,
		ProviderBody:   raw,
		ProviderErrMsg: extractAnthropicErrorMessage(raw),
		RetryAfter:     provider.RetryAfterHeader(resp.Header.Get("Retry-After")),
	}
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
	switch code {
	case http.StatusTooManyRequests, http.StatusInternalServerError,
		http.StatusBadGateway, http.StatusServiceUnavailable, http.StatusGatewayTimeout,
		statusOverloaded:
		return true
	default:
		return false
	}
}

func (c *Client) waitBeforeRetry(ctx context.Context, attempt int, lastErr error) error {
	return provider.WaitBeforeRetry(ctx, c.cfg.RetryBaseDelay, attempt, lastErr)
}
