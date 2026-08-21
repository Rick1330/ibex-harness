package anthropic

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/Rick1330/ibex-harness/packages/crypto"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"
	"go.opentelemetry.io/otel/trace/noop"
)

// Client implements provider.Provider for the Anthropic Messages API.
// Responses are translated to OpenAI-compatible JSON/SSE (ADR-0040).
type Client struct {
	cfg        Config
	httpClient *http.Client
	log        *logger.Logger
	tracer     trace.Tracer
	metrics    Metrics
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
	return &Client{
		cfg: cfg,
		httpClient: &http.Client{
			Timeout: cfg.Timeout,
			Transport: &http.Transport{
				MaxIdleConns:        100,
				MaxIdleConnsPerHost: 20,
				IdleConnTimeout:     90 * time.Second,
				TLSHandshakeTimeout: 10 * time.Second,
			},
		},
		log:     log,
		tracer:  tracer,
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
	return mergeSupportedModels(builtInSupportedModels(), c.cfg.ExtraModels)
}

func mergeSupportedModels(base, extra []string) []string {
	out := make([]string, 0, len(base)+len(extra))
	seen := make(map[string]struct{}, len(base)+len(extra))
	for _, m := range base {
		appendUniqueModel(&out, seen, m)
	}
	for _, m := range extra {
		appendUniqueModel(&out, seen, m)
	}
	return out
}

func appendUniqueModel(out *[]string, seen map[string]struct{}, model string) {
	model = strings.TrimSpace(model)
	if model == "" {
		return
	}
	if _, ok := seen[model]; ok {
		return
	}
	seen[model] = struct{}{}
	*out = append(*out, model)
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
		recordSpanErr(span, err)
		return provider.Response{}, err
	}

	url := strings.TrimRight(c.cfg.BaseURL, "/") + "/v1/messages"
	return c.executeWithRetry(ctx, span, upstreamCall{
		URL: url, Body: body, Stream: req.Stream, Model: req.Model,
	})
}

func (c *Client) doRequest(ctx context.Context, call upstreamCall) (*http.Response, error) {
	reqCtx, cancel := c.streamRequestContext(ctx, call.Stream)
	httpReq, err := c.newMessagesRequest(reqCtx, call)
	if err != nil {
		cancel()
		return nil, err
	}
	resp, err := c.httpClientFor(call.Stream).Do(httpReq)
	if err != nil {
		cancel()
		return nil, err
	}
	return attachStreamCancel(resp, call.Stream, cancel), nil
}

func (c *Client) streamRequestContext(ctx context.Context, stream bool) (context.Context, context.CancelFunc) {
	if !stream {
		return ctx, noopCancel
	}
	return context.WithTimeout(ctx, c.cfg.StreamTimeout)
}

func noopCancel() {}

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

func (c *Client) httpClientFor(stream bool) *http.Client {
	if !stream {
		return c.httpClient
	}
	return &http.Client{Transport: c.httpClient.Transport}
}

func attachStreamCancel(resp *http.Response, stream bool, cancel context.CancelFunc) *http.Response {
	if !stream {
		cancel()
		return resp
	}
	resp.Body = &cancelOnClose{ReadCloser: resp.Body, cancel: cancel}
	return resp
}

type cancelOnClose struct {
	io.ReadCloser
	cancel context.CancelFunc
}

func (c *cancelOnClose) Close() error {
	err := c.ReadCloser.Close()
	c.cancel()
	return err
}

func readProviderError(name string, resp *http.Response) *provider.ProviderError {
	raw, _ := io.ReadAll(io.LimitReader(resp.Body, 64*1024))
	msg := extractAnthropicErrorMessage(raw)
	return &provider.ProviderError{
		ProviderName:   name,
		StatusCode:     resp.StatusCode,
		ProviderBody:   raw,
		ProviderErrMsg: msg,
		RetryAfter:     RetryAfterHeader(resp.Header.Get("Retry-After")),
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

func isRetryableTransport(err error) bool {
	if err == nil {
		return false
	}
	if errors.Is(err, context.Canceled) || errors.Is(err, context.DeadlineExceeded) {
		return false
	}
	var netErr net.Error
	if errors.As(err, &netErr) && netErr.Timeout() {
		return true
	}
	var opErr *net.OpError
	return errors.As(err, &opErr)
}

func (c *Client) waitBeforeRetry(ctx context.Context, attempt int, lastErr error) error {
	delay := retryDelay(c.cfg.RetryBaseDelay, attempt)
	var pe *provider.ProviderError
	if errors.As(lastErr, &pe) && pe.StatusCode == http.StatusTooManyRequests && pe.RetryAfter > 0 {
		delay = pe.RetryAfter
	}
	timer := time.NewTimer(delay)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-timer.C:
		return nil
	}
}

func retryDelay(base time.Duration, attempt int) time.Duration {
	if attempt < 1 {
		attempt = 1
	}
	shift := attempt - 1
	if shift > 10 {
		shift = 10
	}
	delay := base * time.Duration(1<<shift)
	delay += crypto.RandomDuration(base)
	if delay > maxRetryBackoff {
		delay = maxRetryBackoff
	}
	return delay
}

func statusClass(code int) string {
	switch {
	case code >= 200 && code < 300:
		return "2xx"
	case code >= 400 && code < 500:
		return "4xx"
	case code >= 500 || code == statusOverloaded:
		return "5xx"
	default:
		return "other"
	}
}

// RetryAfterHeader parses the Retry-After response header when present.
func RetryAfterHeader(hdr string) time.Duration {
	if hdr == "" {
		return 0
	}
	if secs, err := strconv.Atoi(hdr); err == nil && secs > 0 {
		return time.Duration(secs) * time.Second
	}
	if t, err := http.ParseTime(hdr); err == nil {
		d := time.Until(t)
		if d > 0 {
			return d
		}
	}
	return 0
}
