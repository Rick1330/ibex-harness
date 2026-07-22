package openai

import (
	"context"
	"errors"
	"mime"
	"net/http"
	"strings"
	"time"

	"github.com/Rick1330/ibex-harness/packages/provider"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"
)

type attemptResult struct {
	resp       provider.Response
	err        error
	retry      bool
	statusCode int
}

// upstreamCall holds the HTTP payload for an OpenAI chat completion attempt.
type upstreamCall struct {
	URL    string
	Body   []byte
	Stream bool
}

func (c *Client) executeWithRetry(ctx context.Context, span trace.Span, call upstreamCall) (provider.Response, error) {
	var lastErr error
	for attempt := 0; attempt <= c.cfg.maxRetries(); attempt++ {
		if attempt > 0 {
			c.metrics.IncProviderRetry(c.Name())
			if err := c.waitBeforeRetry(ctx, attempt, lastErr); err != nil {
				recordSpanErr(span, err)
				return provider.Response{}, err
			}
		}
		out := c.tryOnce(ctx, call, attempt)
		if out.err == nil {
			return out.resp, nil
		}
		lastErr = out.err
		if !out.retry {
			recordSpanErr(span, lastErr)
			return provider.Response{}, lastErr
		}
	}
	if lastErr == nil {
		lastErr = errors.New("openai request failed")
	}
	recordSpanErr(span, lastErr)
	return provider.Response{}, lastErr
}

func (c *Client) tryOnce(ctx context.Context, call upstreamCall, attempt int) attemptResult {
	start := time.Now()
	resp, err := c.doRequest(ctx, call)
	if err != nil {
		c.metrics.IncProviderRequest(c.Name(), "error")
		retry := isRetryableTransport(err) && attempt < c.cfg.maxRetries()
		return attemptResult{err: err, retry: retry}
	}

	c.metrics.IncProviderRequest(c.Name(), statusClass(resp.StatusCode))
	if resp.StatusCode == http.StatusOK {
		return c.acceptOKBody(resp, call.Stream, start)
	}

	provErr := readProviderError(c.Name(), resp)
	_ = resp.Body.Close()
	retry := isRetryableStatus(resp.StatusCode) && attempt < c.cfg.maxRetries()
	return attemptResult{err: provErr, retry: retry, statusCode: resp.StatusCode}
}

func (c *Client) acceptOKBody(resp *http.Response, stream bool, start time.Time) attemptResult {
	if stream && !isEventStream(resp.Header.Get("Content-Type")) {
		_ = resp.Body.Close()
		return attemptResult{
			err: &provider.ProviderError{
				ProviderName:   c.Name(),
				StatusCode:     http.StatusBadGateway,
				ProviderErrMsg: "upstream did not return text/event-stream",
			},
		}
	}
	// Live SSE body: never retry after this point (ADR-0027).
	return attemptResult{
		resp: provider.Response{
			Body:       resp.Body,
			StatusCode: resp.StatusCode,
			Latency:    time.Since(start),
		},
	}
}

func isEventStream(contentType string) bool {
	if mediaType, _, err := mime.ParseMediaType(contentType); err == nil {
		return mediaType == "text/event-stream"
	}
	// Fallback: base type before params, tolerate malformed parameters.
	base := strings.TrimSpace(strings.SplitN(contentType, ";", 2)[0])
	return strings.EqualFold(base, "text/event-stream")
}

func recordSpanErr(span trace.Span, err error) {
	if err == nil {
		return
	}
	span.RecordError(err)
	span.SetStatus(codes.Error, err.Error())
}
