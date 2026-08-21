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
	resp, err := c.doRequest(ctx, call)
	if err != nil {
		c.metrics.IncProviderRequest(c.Name(), "error")
		return provider.AttemptOutcome{
			Err:   err,
			Retry: provider.IsRetryableTransport(err) && attempt < c.cfg.maxRetries(),
		}
	}

	c.metrics.IncProviderRequest(c.Name(), provider.StatusClass(resp.StatusCode))
	if resp.StatusCode == http.StatusOK {
		return c.acceptOKBody(resp, call.Stream, start)
	}

	provErr := readProviderError(c.Name(), resp)
	_ = resp.Body.Close()
	return provider.AttemptOutcome{
		Err:   provErr,
		Retry: isRetryableStatus(resp.StatusCode) && attempt < c.cfg.maxRetries(),
	}
}

func (c *Client) acceptOKBody(resp *http.Response, stream bool, start time.Time) provider.AttemptOutcome {
	if stream && !provider.IsEventStream(resp.Header.Get("Content-Type")) {
		_ = resp.Body.Close()
		return provider.AttemptOutcome{
			Err: &provider.ProviderError{
				ProviderName:   c.Name(),
				StatusCode:     http.StatusBadGateway,
				ProviderErrMsg: "upstream did not return text/event-stream",
			},
		}
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
