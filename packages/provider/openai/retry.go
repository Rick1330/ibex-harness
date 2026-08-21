package openai

import (
	"context"
	"net/http"
	"time"

	"github.com/Rick1330/ibex-harness/packages/provider"
	"go.opentelemetry.io/otel/trace"
)

// upstreamCall holds the HTTP payload for an OpenAI chat completion attempt.
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
		"openai request failed",
		c.waitBeforeRetry,
		func() { c.metrics.IncProviderRetry(c.Name()) },
		func(ctx context.Context, attempt int) provider.AttemptOutcome {
			return c.tryOnce(ctx, call, attempt)
		},
	)
}

func (c *Client) tryOnce(ctx context.Context, call upstreamCall, attempt int) provider.AttemptOutcome {
	start := time.Now()
	return provider.TryHTTPOnce(
		c.cfg.maxRetries(),
		attempt,
		func() (*http.Response, error) { return c.doRequest(ctx, call) },
		func(statusClass string) { c.metrics.IncProviderRequest(c.Name(), statusClass) },
		isRetryableStatus,
		func(resp *http.Response) *provider.ProviderError { return readProviderError(c.Name(), resp) },
		func(resp *http.Response) provider.AttemptOutcome {
			return c.acceptOKBody(resp, call.Stream, start)
		},
	)
}

func (c *Client) acceptOKBody(resp *http.Response, stream bool, start time.Time) provider.AttemptOutcome {
	if stream && !provider.IsEventStream(resp.Header.Get("Content-Type")) {
		return provider.NonEventStreamError(c.Name(), resp)
	}
	// Live SSE body: never retry after this point (ADR-0027).
	return provider.AttemptOutcome{
		Resp: provider.Response{
			Body:       resp.Body,
			StatusCode: resp.StatusCode,
			Latency:    time.Since(start),
		},
	}
}
