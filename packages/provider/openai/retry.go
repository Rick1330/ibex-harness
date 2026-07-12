package openai

import (
	"context"
	"errors"
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

func (c *Client) executeWithRetry(ctx context.Context, span trace.Span, url string, body []byte) (provider.Response, error) {
	var lastErr error
	for attempt := 0; attempt <= c.cfg.maxRetries(); attempt++ {
		if attempt > 0 {
			c.metrics.IncProviderRetry(c.Name())
			if err := c.waitBeforeRetry(ctx, attempt, lastErr); err != nil {
				recordSpanErr(span, err)
				return provider.Response{}, err
			}
		}
		out := c.tryOnce(ctx, url, body, attempt)
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

func (c *Client) tryOnce(ctx context.Context, url string, body []byte, attempt int) attemptResult {
	start := time.Now()
	resp, err := c.doRequest(ctx, url, body)
	if err != nil {
		c.metrics.IncProviderRequest(c.Name(), "error")
		retry := isRetryableTransport(err) && attempt < c.cfg.maxRetries()
		return attemptResult{err: err, retry: retry}
	}

	c.metrics.IncProviderRequest(c.Name(), statusClass(resp.StatusCode))
	if resp.StatusCode == http.StatusOK {
		return attemptResult{
			resp: provider.Response{
				Body:       resp.Body,
				StatusCode: resp.StatusCode,
				Latency:    time.Since(start),
			},
		}
	}

	provErr := readProviderError(c.Name(), resp)
	_ = resp.Body.Close()
	retry := isRetryableStatus(resp.StatusCode) && attempt < c.cfg.maxRetries()
	return attemptResult{err: provErr, retry: retry, statusCode: resp.StatusCode}
}

func recordSpanErr(span trace.Span, err error) {
	if err == nil {
		return
	}
	span.RecordError(err)
	span.SetStatus(codes.Error, err.Error())
}
