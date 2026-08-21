package openaicompatible

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/Rick1330/ibex-harness/packages/circuitbreaker"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"go.opentelemetry.io/otel/trace"
)

// Client implements provider.Provider for OpenAI-compatible chat APIs.
type Client struct {
	cfg          Config
	httpClient   *http.Client
	streamClient *http.Client
	log          *logger.Logger
	tracer       trace.Tracer
	metrics      Metrics
}

// New constructs a Client. cfg.ProviderName and cfg.BaseURL are required.
func New(cfg Config, log *logger.Logger, tracer trace.Tracer, metrics Metrics) *Client {
	cfg.ApplyDefaults()
	if metrics == nil {
		metrics = noopMetrics{}
	}
	name := strings.TrimSpace(cfg.ProviderName)
	if name == "" {
		name = ProviderNameSelfHosted
		cfg.ProviderName = name
	}
	clients := provider.NewHTTPClients(cfg.Timeout)
	return &Client{
		cfg:          cfg,
		httpClient:   clients.Sync,
		streamClient: clients.Stream,
		log:          log,
		tracer:       provider.TracerOrNoop(tracer, name),
		metrics:      metrics,
	}
}

func (c *Client) Name() string { return c.cfg.ProviderName }

// SupportedModels returns built-ins ∪ ExtraModels.
func (c *Client) SupportedModels() []string {
	return provider.MergeSupportedModels(c.cfg.BuiltInModels, c.cfg.ExtraModels)
}

// Complete sends a chat completion request to the configured BaseURL.
func (c *Client) Complete(ctx context.Context, req provider.Request) (provider.Response, error) {
	if c.cfg.Breaker == nil {
		return c.completeOnce(ctx, req)
	}
	out, err := c.cfg.Breaker.Execute(func() (any, error) {
		resp, err := c.completeOnce(ctx, req)
		if err != nil {
			return nil, err
		}
		return resp, nil
	})
	if err != nil {
		var pe *provider.ProviderError
		if errors.As(err, &pe) {
			return provider.Response{}, pe
		}
		if errors.Is(err, circuitbreaker.ErrOpen) {
			return provider.Response{}, &provider.ProviderError{
				ProviderName:   c.Name(),
				StatusCode:     http.StatusServiceUnavailable,
				ProviderErrMsg: "circuit breaker open",
				Reason:         provider.ErrorReasonCircuitOpen,
			}
		}
		return provider.Response{}, err
	}
	return out.(provider.Response), nil
}

func (c *Client) completeOnce(ctx context.Context, req provider.Request) (provider.Response, error) {
	ctx, span := provider.StartCompleteSpan(ctx, c.tracer, provider.CompleteSpan{
		Names: provider.CompleteSpanNames{Span: c.Name() + ".Complete", Provider: c.Name()},
		Req:   req,
	})
	defer span.End()

	body, err := marshalOpenAIRequestBody(req)
	if err != nil {
		provider.RecordSpanErr(span, err)
		return provider.Response{}, fmt.Errorf("%s request: %w", c.Name(), err)
	}

	return c.executeWithRetry(ctx, span, upstreamCall{
		URL:    provider.JoinBaseURL(c.cfg.BaseURL, "/chat/completions"),
		Body:   body,
		Stream: req.Stream,
	})
}

type upstreamCall struct {
	URL    string
	Body   []byte
	Stream bool
}

func (c *Client) executeWithRetry(ctx context.Context, span trace.Span, call upstreamCall) (provider.Response, error) {
	return provider.WithRetries(
		ctx,
		span,
		c.cfg.maxRetries(),
		c.Name()+" request failed",
		c.waitBeforeRetry,
		func() { c.metrics.IncProviderRetry(c.Name()) },
		func(ctx context.Context, attempt int) provider.AttemptOutcome {
			return c.tryOnce(ctx, call, attempt)
		},
	)
}

func (c *Client) tryOnce(ctx context.Context, call upstreamCall, attempt int) provider.AttemptOutcome {
	return provider.TimedHTTPOnce(
		c.cfg.maxRetries(),
		attempt,
		func() (*http.Response, error) { return c.doRequest(ctx, call) },
		func(statusClass string) { c.metrics.IncProviderRequest(c.Name(), statusClass) },
		func(code int) bool { return provider.IsRetryableHTTPStatus(code) },
		func(resp *http.Response) *provider.ProviderError { return readProviderError(c.Name(), resp) },
		func(resp *http.Response, latency time.Duration) provider.AttemptOutcome {
			return c.acceptOKBody(resp, call.Stream, latency)
		},
	)
}

func (c *Client) acceptOKBody(resp *http.Response, stream bool, latency time.Duration) provider.AttemptOutcome {
	if stream && !provider.IsEventStream(resp.Header.Get("Content-Type")) {
		return provider.NonEventStreamError(c.Name(), resp)
	}
	return provider.AttemptOutcome{
		Resp: provider.Response{
			Body:       resp.Body,
			StatusCode: resp.StatusCode,
			Latency:    latency,
		},
	}
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
	headers := map[string]string{"Content-Type": "application/json"}
	key := strings.TrimSpace(c.cfg.APIKey)
	switch c.cfg.AuthMode {
	case AuthBearerOmitEmpty:
		if key != "" {
			headers["Authorization"] = "Bearer " + key
		}
	default:
		headers["Authorization"] = "Bearer " + key
	}
	return provider.NewJSONPostRequest(ctx, call, headers)
}

func readProviderError(name string, resp *http.Response) *provider.ProviderError {
	pe := provider.ReadProviderError(name, resp, extractOpenAIErrorMessage)
	if pe != nil && pe.StatusCode == http.StatusServiceUnavailable {
		pe.Reason = provider.ErrorReasonQueueFull
	}
	return pe
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
