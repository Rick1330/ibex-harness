package anthropic

import (
	"context"
	"io"
	"net/http"
	"time"

	"github.com/Rick1330/ibex-harness/packages/provider"
	"go.opentelemetry.io/otel/trace"
)

type upstreamCall struct {
	URL    string
	Body   []byte
	Stream bool
	Model  string
}

func (c *Client) executeWithRetry(ctx context.Context, span trace.Span, call upstreamCall) (provider.Response, error) {
	return provider.WithRetries(
		ctx,
		span,
		c.cfg.maxRetries(),
		"anthropic request failed",
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
			return c.acceptOKBody(resp, call, start)
		},
	)
}

func (c *Client) acceptOKBody(resp *http.Response, call upstreamCall, start time.Time) provider.AttemptOutcome {
	requestID := firstNonEmpty(resp.Header.Get("request-id"), resp.Header.Get("x-request-id"))
	latency := time.Since(start)
	if call.Stream {
		return c.acceptStreamBody(resp, call.Model, requestID, latency)
	}
	return c.acceptJSONBody(resp, call.Model, requestID, latency)
}

func (c *Client) acceptStreamBody(resp *http.Response, model, requestID string, latency time.Duration) provider.AttemptOutcome {
	if !provider.IsEventStream(resp.Header.Get("Content-Type")) {
		return provider.NonEventStreamError(c.Name(), resp)
	}
	// Live SSE body: never retry after this point (ADR-0027 / ADR-0040).
	pipe := newStreamTranslatePipe(resp.Body, model, requestID)
	return provider.AttemptOutcome{
		Resp: provider.Response{
			Body:              pipe,
			StatusCode:        http.StatusOK,
			Latency:           latency,
			ProviderRequestID: requestID,
		},
	}
}

func (c *Client) acceptJSONBody(resp *http.Response, model, requestID string, latency time.Duration) provider.AttemptOutcome {
	raw, err := io.ReadAll(io.LimitReader(resp.Body, 8<<20))
	_ = resp.Body.Close()
	if err != nil {
		return provider.AttemptOutcome{Err: err}
	}
	translated, err := translateNonStreamResponse(raw, model, requestID, latency)
	if err != nil {
		return provider.AttemptOutcome{Err: err}
	}
	return provider.AttemptOutcome{Resp: translated}
}

func firstNonEmpty(values ...string) string {
	for _, v := range values {
		if v != "" {
			return v
		}
	}
	return ""
}
