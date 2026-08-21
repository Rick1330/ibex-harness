package provider

import (
	"context"
	"errors"
	"io"
	"mime"
	"net"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/Rick1330/ibex-harness/packages/crypto"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"
)

const (
	// DefaultMaxRetryBackoff caps exponential retry sleep across provider clients.
	DefaultMaxRetryBackoff = 30 * time.Second
)

// MergeSupportedModels concatenates base and extra model IDs with trim + dedupe.
func MergeSupportedModels(base, extra []string) []string {
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

// NewPooledHTTPClient builds an upstream client with connection pooling defaults.
func NewPooledHTTPClient(timeout time.Duration) *http.Client {
	return &http.Client{
		Timeout: timeout,
		Transport: &http.Transport{
			MaxIdleConns:        100,
			MaxIdleConnsPerHost: 20,
			IdleConnTimeout:     90 * time.Second,
			TLSHandshakeTimeout: 10 * time.Second,
		},
	}
}

// StreamHTTPClient returns a client that shares Transport but has no Client.Timeout
// so long-lived SSE streams are bounded only by request context.
func StreamHTTPClient(base *http.Client) *http.Client {
	return &http.Client{Transport: base.Transport}
}

// NoopCancel is used when a call shares the parent context (no derived deadline).
func NoopCancel() {
	_ = struct{}{}
}

// StreamRequestContext derives a timeout only for streaming calls.
func StreamRequestContext(ctx context.Context, stream bool, streamTimeout time.Duration) (context.Context, context.CancelFunc) {
	if !stream {
		return ctx, NoopCancel
	}
	return context.WithTimeout(ctx, streamTimeout)
}

// CancelOnClose cancels the request context when the response body is closed.
type CancelOnClose struct {
	io.ReadCloser
	Cancel context.CancelFunc
}

// Close closes the underlying body then cancels the request context.
func (c *CancelOnClose) Close() error {
	err := c.ReadCloser.Close()
	c.Cancel()
	return err
}

// AttachStreamCancel wraps a streaming response body so Close cancels the request.
// For non-stream responses the cancel func is invoked immediately.
func AttachStreamCancel(resp *http.Response, stream bool, cancel context.CancelFunc) *http.Response {
	if !stream {
		cancel()
		return resp
	}
	resp.Body = &CancelOnClose{ReadCloser: resp.Body, Cancel: cancel}
	return resp
}

// IsRetryableTransport reports pre-delivery connection failures worth retrying.
// Timeouts and context errors are not retried: for non-idempotent POSTs the
// request may already have been accepted upstream (duplicate completion risk).
func IsRetryableTransport(err error) bool {
	if err == nil {
		return false
	}
	if errors.Is(err, context.Canceled) || errors.Is(err, context.DeadlineExceeded) {
		return false
	}
	var netErr net.Error
	if errors.As(err, &netErr) && netErr.Timeout() {
		return false
	}
	var opErr *net.OpError
	if !errors.As(err, &opErr) {
		return false
	}
	switch opErr.Op {
	case "dial", "connect":
		return true
	default:
		return false
	}
}

// RetryDelay computes exponential backoff with jitter, capped at maxBackoff.
func RetryDelay(base time.Duration, attempt int, maxBackoff time.Duration) time.Duration {
	if attempt < 1 {
		attempt = 1
	}
	shift := attempt - 1
	if shift > 10 {
		shift = 10
	}
	delay := base * time.Duration(1<<shift)
	delay += crypto.RandomDuration(base)
	if maxBackoff <= 0 {
		maxBackoff = DefaultMaxRetryBackoff
	}
	if delay > maxBackoff {
		return maxBackoff
	}
	return delay
}

// RetryAfterFromError returns Retry-After for rate-limit / overload / unavailable errors.
func RetryAfterFromError(lastErr error) time.Duration {
	var pe *ProviderError
	if !errors.As(lastErr, &pe) || pe.RetryAfter <= 0 {
		return 0
	}
	switch pe.StatusCode {
	case http.StatusTooManyRequests, http.StatusServiceUnavailable, 529:
		return pe.RetryAfter
	default:
		return 0
	}
}

// WaitBeforeRetry sleeps for backoff (honoring Retry-After hints) or returns ctx err.
func WaitBeforeRetry(ctx context.Context, base time.Duration, attempt int, lastErr error) error {
	delay := RetryDelay(base, attempt, DefaultMaxRetryBackoff)
	if ra := RetryAfterFromError(lastErr); ra > 0 {
		delay = ra
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

// StatusClass maps an HTTP status to a coarse metrics label.
func StatusClass(code int) string {
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

// IsEventStream reports whether Content-Type is text/event-stream.
func IsEventStream(contentType string) bool {
	if mediaType, _, err := mime.ParseMediaType(contentType); err == nil {
		return mediaType == "text/event-stream"
	}
	base := strings.TrimSpace(strings.SplitN(contentType, ";", 2)[0])
	return strings.EqualFold(base, "text/event-stream")
}

// RecordSpanErr marks a span as failed when err is non-nil.
func RecordSpanErr(span trace.Span, err error) {
	if err == nil {
		return
	}
	span.RecordError(err)
	span.SetStatus(codes.Error, err.Error())
}

// AttemptOutcome is one Complete attempt inside WithRetries.
type AttemptOutcome struct {
	Resp  Response
	Err   error
	Retry bool
}

// WithRetries runs tryOnce with exponential backoff until success, non-retry, or budget exhausted.
func WithRetries(
	ctx context.Context,
	span trace.Span,
	maxRetries int,
	exhaustedMsg string,
	wait func(context.Context, int, error) error,
	onRetry func(),
	tryOnce func(context.Context, int) AttemptOutcome,
) (Response, error) {
	var lastErr error
	for attempt := 0; attempt <= maxRetries; attempt++ {
		if attempt > 0 {
			onRetry()
			if err := wait(ctx, attempt, lastErr); err != nil {
				RecordSpanErr(span, err)
				return Response{}, err
			}
		}
		out := tryOnce(ctx, attempt)
		if out.Err == nil {
			return out.Resp, nil
		}
		lastErr = out.Err
		if !out.Retry {
			RecordSpanErr(span, lastErr)
			return Response{}, lastErr
		}
	}
	if lastErr == nil {
		lastErr = errors.New(exhaustedMsg)
	}
	RecordSpanErr(span, lastErr)
	return Response{}, lastErr
}
