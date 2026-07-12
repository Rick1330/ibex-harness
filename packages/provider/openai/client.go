package openai

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
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

// Client implements provider.Provider for the OpenAI API.
type Client struct {
	cfg        Config
	httpClient *http.Client
	log        *logger.Logger
	tracer     trace.Tracer
	metrics    Metrics
}

// New constructs an OpenAI Client with a shared http.Client for connection pooling.
func New(cfg Config, log *logger.Logger, tracer trace.Tracer, metrics Metrics) *Client {
	cfg.ApplyDefaults()
	if metrics == nil {
		metrics = noopMetrics{}
	}
	if tracer == nil {
		tracer = noop.NewTracerProvider().Tracer("openai")
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

func (c *Client) Name() string { return "openai" }

func (c *Client) SupportedModels() []string {
	return []string{"gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"}
}

// Complete sends a non-streaming chat completion request to OpenAI.
func (c *Client) Complete(ctx context.Context, req provider.Request) (provider.Response, error) {
	ctx, span := c.tracer.Start(ctx, "openai.Complete",
		trace.WithAttributes(
			attribute.String("provider.name", c.Name()),
			attribute.String("llm.model", req.Model),
			attribute.Bool("llm.stream", req.Stream),
		),
	)
	defer span.End()

	body, err := c.marshalRequest(req)
	if err != nil {
		recordSpanErr(span, err)
		return provider.Response{}, err
	}

	url := strings.TrimRight(c.cfg.BaseURL, "/") + "/chat/completions"
	return c.executeWithRetry(ctx, span, url, body)
}

func (c *Client) marshalRequest(req provider.Request) ([]byte, error) {
	body, err := marshalOpenAIRequestBody(req)
	if err != nil {
		return nil, fmt.Errorf("openai request: %w", err)
	}
	return body, nil
}

func (c *Client) doRequest(ctx context.Context, url string, body []byte) (*http.Response, error) {
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Authorization", "Bearer "+c.cfg.APIKey)
	return c.httpClient.Do(httpReq)
}

func readProviderError(name string, resp *http.Response) *provider.ProviderError {
	raw, _ := io.ReadAll(io.LimitReader(resp.Body, 64*1024))
	msg := extractOpenAIErrorMessage(raw)
	return &provider.ProviderError{
		ProviderName:   name,
		StatusCode:     resp.StatusCode,
		ProviderBody:   raw,
		ProviderErrMsg: msg,
		RetryAfter:     RetryAfterHeader(resp.Header.Get("Retry-After")),
	}
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
	switch code {
	case http.StatusTooManyRequests, http.StatusInternalServerError,
		http.StatusBadGateway, http.StatusServiceUnavailable, http.StatusGatewayTimeout:
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
	if pe, ok := lastErr.(*provider.ProviderError); ok && pe.StatusCode == http.StatusTooManyRequests {
		if pe.RetryAfter > 0 {
			delay = pe.RetryAfter
		} else if ra := retryAfterFromProvider(pe); ra > 0 {
			delay = ra
		}
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

func statusClass(code int) string {
	switch {
	case code >= 200 && code < 300:
		return "2xx"
	case code >= 400 && code < 500:
		return "4xx"
	case code >= 500:
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
