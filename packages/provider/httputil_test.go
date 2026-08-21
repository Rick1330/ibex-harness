package provider

import (
	"context"
	"errors"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"go.opentelemetry.io/otel/trace/noop"
)

func TestMergeSupportedModels(t *testing.T) {
	t.Parallel()
	got := MergeSupportedModels([]string{"a", "b"}, []string{" b ", "c", "", "a"})
	if len(got) != 3 || got[0] != "a" || got[1] != "b" || got[2] != "c" {
		t.Fatalf("got=%v", got)
	}
}

func TestStatusClass(t *testing.T) {
	t.Parallel()
	cases := map[int]string{200: "2xx", 404: "4xx", 500: "5xx", 529: "5xx", 100: "other"}
	for code, want := range cases {
		if got := StatusClass(code); got != want {
			t.Fatalf("StatusClass(%d)=%q want %q", code, got, want)
		}
	}
}

func TestRetryAfterHeader(t *testing.T) {
	t.Parallel()
	if RetryAfterHeader("") != 0 {
		t.Fatal("empty")
	}
	if RetryAfterHeader("2") != 2*time.Second {
		t.Fatal("seconds")
	}
	if RetryAfterHeader("nope") != 0 {
		t.Fatal("invalid")
	}
	future := time.Now().Add(30 * time.Second).UTC().Format(http.TimeFormat)
	if RetryAfterHeader(future) <= 0 {
		t.Fatal("http-date")
	}
	past := time.Now().Add(-30 * time.Second).UTC().Format(http.TimeFormat)
	if RetryAfterHeader(past) != 0 {
		t.Fatal("past http-date")
	}
}

func TestIsEventStream(t *testing.T) {
	t.Parallel()
	if !IsEventStream("text/event-stream") {
		t.Fatal("plain")
	}
	if !IsEventStream("text/event-stream; charset=utf-8") {
		t.Fatal("params")
	}
	if !IsEventStream("TEXT/EVENT-STREAM") {
		t.Fatal("case")
	}
	if IsEventStream("application/json") {
		t.Fatal("json")
	}
	if IsEventStream("") {
		t.Fatal("empty")
	}
}

func TestRetryAfterFromError(t *testing.T) {
	t.Parallel()
	pe := &ProviderError{StatusCode: 429, RetryAfter: 3 * time.Second}
	if got := RetryAfterFromError(pe); got != 3*time.Second {
		t.Fatalf("got=%v", got)
	}
	if RetryAfterFromError(&ProviderError{StatusCode: 500, RetryAfter: time.Second}) != 0 {
		t.Fatal("non-hint status")
	}
	if got := RetryAfterFromError(&ProviderError{StatusCode: 529, RetryAfter: time.Second}); got != time.Second {
		t.Fatalf("529 got=%v", got)
	}
	if got := RetryAfterFromError(&ProviderError{StatusCode: 503, RetryAfter: 2 * time.Second}); got != 2*time.Second {
		t.Fatalf("503 got=%v", got)
	}
}

func TestIsRetryableTransport(t *testing.T) {
	t.Parallel()
	if IsRetryableTransport(nil) || IsRetryableTransport(context.Canceled) || IsRetryableTransport(context.DeadlineExceeded) {
		t.Fatal("nil/cancel/deadline")
	}
	if IsRetryableTransport(timeoutNetError{}) {
		t.Fatal("timeout")
	}
	if !IsRetryableTransport(&net.OpError{Op: "dial", Err: errors.New("refused")}) {
		t.Fatal("dial")
	}
	if !IsRetryableTransport(&net.OpError{Op: "connect", Err: errors.New("refused")}) {
		t.Fatal("connect")
	}
	if IsRetryableTransport(&net.OpError{Op: "write", Err: errors.New("reset")}) {
		t.Fatal("write")
	}
}

type timeoutNetError struct{}

func (timeoutNetError) Error() string   { return "timeout" }
func (timeoutNetError) Timeout() bool   { return true }
func (timeoutNetError) Temporary() bool { return true }

func TestRetryDelayAndWait(t *testing.T) {
	t.Parallel()
	if got := RetryDelay(time.Millisecond, 0, time.Second); got <= 0 {
		t.Fatal("delay")
	}
	if got := RetryDelay(time.Second, 100, 50*time.Millisecond); got != 50*time.Millisecond {
		t.Fatalf("cap=%v", got)
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if err := WaitBeforeRetry(ctx, time.Second, 1, nil); err == nil {
		t.Fatal("expected cancel")
	}
	if err := WaitBeforeRetry(context.Background(), time.Millisecond, 1, &ProviderError{
		StatusCode: 429, RetryAfter: time.Millisecond,
	}); err != nil {
		t.Fatal(err)
	}
}

func TestStreamHelpers(t *testing.T) {
	t.Parallel()
	client := NewPooledHTTPClient(time.Second)
	if client.Timeout != time.Second || client.Transport == nil {
		t.Fatal("pooled")
	}
	stream := StreamHTTPClient(client)
	if stream.Timeout != 0 || stream.Transport != client.Transport {
		t.Fatal("stream client")
	}
	NoopCancel()
	NoopCancel() // exercise empty body for coverage

	ctx, cancel := StreamRequestContext(context.Background(), false, time.Minute)
	if ctx != context.Background() {
		t.Fatal("non-stream ctx")
	}
	cancel()
	ctx, cancel = StreamRequestContext(context.Background(), true, time.Minute)
	cancel()
	if _, ok := ctx.Deadline(); !ok {
		t.Fatal("stream deadline")
	}

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte("ok"))
	}))
	t.Cleanup(srv.Close)
	resp, err := http.Get(srv.URL)
	if err != nil {
		t.Fatal(err)
	}
	called := false
	wrapped := AttachStreamCancel(resp, true, func() { called = true })
	_ = wrapped.Body.Close()
	if !called {
		t.Fatal("cancel not called")
	}

	resp2, err := http.Get(srv.URL)
	if err != nil {
		t.Fatal(err)
	}
	canceled := false
	_ = AttachStreamCancel(resp2, false, func() { canceled = true })
	_ = resp2.Body.Close()
	if !canceled {
		t.Fatal("non-stream cancel")
	}
}

func TestWithRetries(t *testing.T) {
	t.Parallel()
	tr := noop.NewTracerProvider().Tracer("t")
	ctx, span := tr.Start(context.Background(), "t")
	defer span.End()

	attempts := 0
	resp, err := WithRetries(ctx, span, 2, "exhausted",
		func(context.Context, int, error) error { return nil },
		func() {},
		func(context.Context, int) AttemptOutcome {
			attempts++
			if attempts < 2 {
				return AttemptOutcome{Err: errors.New("temp"), Retry: true}
			}
			return AttemptOutcome{Resp: Response{StatusCode: 200, Body: io.NopCloser(strings.NewReader("ok"))}}
		},
	)
	if err != nil || resp.StatusCode != 200 {
		t.Fatalf("err=%v status=%d", err, resp.StatusCode)
	}
	_ = resp.Body.Close()

	_, err = WithRetries(ctx, span, 0, "exhausted",
		func(context.Context, int, error) error { return nil },
		func() {},
		func(context.Context, int) AttemptOutcome {
			return AttemptOutcome{Err: errors.New("fail"), Retry: false}
		},
	)
	if err == nil {
		t.Fatal("expected fail")
	}

	_, err = WithRetries(ctx, span, 1, "exhausted",
		func(context.Context, int, error) error { return context.Canceled },
		func() {},
		func(context.Context, int) AttemptOutcome {
			return AttemptOutcome{Err: errors.New("temp"), Retry: true}
		},
	)
	if !errors.Is(err, context.Canceled) {
		t.Fatalf("wait cancel: %v", err)
	}

	_, err = WithRetries(ctx, span, 0, "exhausted",
		func(context.Context, int, error) error { return nil },
		func() {},
		func(context.Context, int) AttemptOutcome {
			return AttemptOutcome{Err: errors.New("x"), Retry: true}
		},
	)
	if err == nil {
		t.Fatal("expected exhausted path error")
	}

	RecordSpanErr(span, errors.New("x"))
	RecordSpanErr(span, nil)
}

func TestCancelOnClose(t *testing.T) {
	t.Parallel()
	canceled := false
	c := &CancelOnClose{
		ReadCloser: io.NopCloser(strings.NewReader("x")),
		Cancel:     func() { canceled = true },
	}
	if err := c.Close(); err != nil {
		t.Fatal(err)
	}
	if !canceled {
		t.Fatal("cancel")
	}
}
