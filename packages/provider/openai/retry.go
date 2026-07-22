package openai

import (
	"context"
	"errors"
	"mime"
	"net/http"
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

type retryCall struct {
	ctx    context.Context
	span   trace.Span
	url    string
	body   []byte
	stream bool
}

type tryOnceCall struct {
	ctx     context.Context
	url     string
	body    []byte
	attempt int
	stream  bool
}

func (c *Client) executeWithRetry(call retryCall) (provider.Response, error) {
	var lastErr error
	for attempt := 0; attempt <= c.cfg.maxRetries(); attempt++ {
		if attempt > 0 {
			c.metrics.IncProviderRetry(c.Name())
			if err := c.waitBeforeRetry(call.ctx, attempt, lastErr); err != nil {
				recordSpanErr(call.span, err)
				return provider.Response{}, err
			}
		}
		out := c.tryOnce(tryOnceCall{
			ctx: call.ctx, url: call.url, body: call.body, attempt: attempt, stream: call.stream,
		})
		if out.err == nil {
			return out.resp, nil
		}
		lastErr = out.err
		if !out.retry {
			recordSpanErr(call.span, lastErr)
			return provider.Response{}, lastErr
		}
	}
	if lastErr == nil {
		lastErr = errors.New("openai request failed")
	}
	recordSpanErr(call.span, lastErr)
	return provider.Response{}, lastErr
}

func (c *Client) tryOnce(call tryOnceCall) attemptResult {
	start := time.Now()
	resp, err := c.doRequest(call.ctx, call.url, call.body, call.stream)
	if err != nil {
		c.metrics.IncProviderRequest(c.Name(), "error")
		retry := isRetryableTransport(err) && call.attempt < c.cfg.maxRetries()
		return attemptResult{err: err, retry: retry}
	}

	c.metrics.IncProviderRequest(c.Name(), statusClass(resp.StatusCode))
	if resp.StatusCode == http.StatusOK {
		return c.acceptOKBody(resp, call.stream, start)
	}

	provErr := readProviderError(c.Name(), resp)
	_ = resp.Body.Close()
	retry := isRetryableStatus(resp.StatusCode) && call.attempt < c.cfg.maxRetries()
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
	mediaType, _, err := mime.ParseMediaType(contentType)
	if err != nil {
		return false
	}
	return mediaType == "text/event-stream"
}

func recordSpanErr(span trace.Span, err error) {
	if err == nil {
		return
	}
	span.RecordError(err)
	span.SetStatus(codes.Error, err.Error())
}
