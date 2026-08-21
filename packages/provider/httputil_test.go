package provider

import (
	"bytes"
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
	want := []string{"a", "b", "c"}
	if len(got) != len(want) {
		t.Fatalf("got=%v", got)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("got=%v", got)
		}
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
	assertNotRetryable(t, nil)
	assertNotRetryable(t, context.Canceled)
	assertNotRetryable(t, context.DeadlineExceeded)
	assertNotRetryable(t, timeoutNetError{})
	assertNotRetryable(t, &net.OpError{Op: "write", Err: errors.New("reset")})
	if !IsRetryableTransport(&net.OpError{Op: "dial", Err: errors.New("refused")}) {
		t.Fatal("dial")
	}
	if !IsRetryableTransport(&net.OpError{Op: "connect", Err: errors.New("refused")}) {
		t.Fatal("connect")
	}
}

func assertNotRetryable(t *testing.T, err error) {
	t.Helper()
	if IsRetryableTransport(err) {
		t.Fatalf("unexpected retryable: %v", err)
	}
}

type timeoutNetError struct{}

func (timeoutNetError) Error() string   { return "timeout" }
func (timeoutNetError) Timeout() bool   { return true }
func (timeoutNetError) Temporary() bool { return true }

func TestRetryDelayAndWait(t *testing.T) {
	t.Parallel()
	if RetryDelay(time.Millisecond, 0, time.Second) <= 0 {
		t.Fatal("delay")
	}
	if RetryDelay(time.Second, 100, 50*time.Millisecond) != 50*time.Millisecond {
		t.Fatal("cap")
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
	assertPooledClients(t)
	assertStreamContext(t)
	assertAttachStreamCancel(t)
}

func assertPooledClients(t *testing.T) {
	t.Helper()
	client := NewPooledHTTPClient(time.Second)
	if client.Timeout != time.Second || client.Transport == nil {
		t.Fatal("pooled")
	}
	stream := StreamHTTPClient(client)
	if stream.Timeout != 0 || stream.Transport != client.Transport {
		t.Fatal("stream client")
	}
	NoopCancel()
}

func assertStreamContext(t *testing.T) {
	t.Helper()
	ctx, cancel := StreamRequestContext(context.Background(), false, time.Minute)
	cancel()
	if ctx != context.Background() {
		t.Fatal("non-stream ctx")
	}
	ctx, cancel = StreamRequestContext(context.Background(), true, time.Minute)
	cancel()
	if _, ok := ctx.Deadline(); !ok {
		t.Fatal("stream deadline")
	}
}

func assertAttachStreamCancel(t *testing.T) {
	t.Helper()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte("ok"))
	}))
	t.Cleanup(srv.Close)

	resp, err := http.Get(srv.URL)
	if err != nil {
		t.Fatal(err)
	}
	called := false
	resp = AttachStreamCancel(resp, true, func() { called = true })
	if err := resp.Body.Close(); err != nil {
		t.Fatal(err)
	}
	if !called {
		t.Fatal("cancel not called")
	}

	resp2, err := http.Get(srv.URL)
	if err != nil {
		t.Fatal(err)
	}
	canceled := false
	_ = AttachStreamCancel(resp2, false, func() { canceled = true })
	defer func() { _ = resp2.Body.Close() }()
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

func TestNewHTTPClients(t *testing.T) {
	t.Parallel()
	clients := NewHTTPClients(time.Second)
	if clients.Sync == nil {
		t.Fatal("sync")
	}
	if clients.Stream == nil {
		t.Fatal("stream")
	}
	if clients.Sync.Transport != clients.Stream.Transport {
		t.Fatal("shared transport")
	}
}

func TestTracerOrNoop(t *testing.T) {
	t.Parallel()
	if TracerOrNoop(nil, "x") == nil {
		t.Fatal("noop tracer")
	}
	tr := noop.NewTracerProvider().Tracer("t")
	if TracerOrNoop(tr, "x") != tr {
		t.Fatal("passthrough tracer")
	}
}

func TestStartCompleteSpanAndJoin(t *testing.T) {
	t.Parallel()
	tr := noop.NewTracerProvider().Tracer("t")
	ctx, span := StartCompleteSpan(context.Background(), tr, CompleteSpanNames{
		Span: "prov.Complete", Provider: "prov",
	}, Request{Model: "m", Stream: true})
	span.End()
	if ctx == nil {
		t.Fatal("span ctx")
	}
	if JoinBaseURL("https://api.example/", "/v1/x") != "https://api.example/v1/x" {
		t.Fatal("join")
	}
}

func TestNewJSONPostAndTimedOnce(t *testing.T) {
	t.Parallel()
	req, err := NewJSONPostRequest(context.Background(), UpstreamCall{
		URL: "http://example.invalid", Body: []byte(`{}`), Stream: true,
	}, map[string]string{"Content-Type": "application/json"})
	if err != nil {
		t.Fatal(err)
	}
	if req.Header.Get("Accept") != "text/event-stream" {
		t.Fatal("accept")
	}
	if req.Header.Get("Content-Type") != "application/json" {
		t.Fatal("content-type")
	}
	out := TimedHTTPOnce(0, 0,
		func() (*http.Response, error) {
			return nil, &net.OpError{Op: "dial", Err: errors.New("refused")}
		},
		func(string) {},
		func(int) bool { return true },
		func(*http.Response) *ProviderError { return nil },
		func(*http.Response, time.Duration) AttemptOutcome { return AttemptOutcome{} },
	)
	if out.Err == nil {
		t.Fatal("expected dial error")
	}
}

func TestIsRetryableHTTPStatus(t *testing.T) {
	t.Parallel()
	if !IsRetryableHTTPStatus(429) {
		t.Fatal("429")
	}
	if !IsRetryableHTTPStatus(529, 529) {
		t.Fatal("529")
	}
	if IsRetryableHTTPStatus(400) {
		t.Fatal("400")
	}
}

func TestDoUpstreamAndReadProviderError(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-Test") != "1" {
			t.Errorf("missing header")
		}
		w.Header().Set("Retry-After", "1")
		http.Error(w, `{"error":{"message":"nope"}}`, http.StatusTooManyRequests)
	}))
	t.Cleanup(srv.Close)

	base := NewPooledHTTPClient(time.Second)
	resp, err := DoUpstream(context.Background(), time.Second, base, StreamHTTPClient(base),
		func(ctx context.Context, call UpstreamCall) (*http.Request, error) {
			req, err := http.NewRequestWithContext(ctx, http.MethodPost, call.URL, bytes.NewReader(call.Body))
			if err != nil {
				return nil, err
			}
			req.Header.Set("X-Test", "1")
			return req, nil
		},
		UpstreamCall{URL: srv.URL, Body: []byte("{}"), Stream: false},
	)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = resp.Body.Close() }()
	pe := ReadProviderError("t", resp, func(raw []byte) string {
		if strings.Contains(string(raw), "nope") {
			return "nope"
		}
		return "upstream provider error"
	})
	if pe.StatusCode != 429 {
		t.Fatalf("status=%d", pe.StatusCode)
	}
	if pe.ProviderErrMsg != "nope" {
		t.Fatalf("msg=%q", pe.ProviderErrMsg)
	}
	if pe.RetryAfter <= 0 {
		t.Fatal("retry-after")
	}
}

func TestNonEventStreamErrorCloses(t *testing.T) {
	t.Parallel()
	okSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{}`))
	}))
	t.Cleanup(okSrv.Close)
	okResp, err := http.Get(okSrv.URL)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = okResp.Body.Close() }()
	out := NonEventStreamError("t", okResp)
	if out.Err == nil {
		t.Fatal("expected non-event-stream error")
	}
}

func TestTryHTTPOnceDialRetry(t *testing.T) {
	t.Parallel()
	attempts := 0
	got := TryHTTPOnce(1, 0,
		func() (*http.Response, error) {
			attempts++
			return nil, &net.OpError{Op: "dial", Err: errors.New("refused")}
		},
		func(string) {},
		func(code int) bool { return IsRetryableHTTPStatus(code) },
		func(*http.Response) *ProviderError { return nil },
		func(*http.Response) AttemptOutcome { return AttemptOutcome{} },
	)
	if got.Err == nil {
		t.Fatal("err")
	}
	if !got.Retry {
		t.Fatal("retry")
	}
	if attempts != 1 {
		t.Fatalf("attempts=%d", attempts)
	}
}

func TestTryHTTPOnceOK(t *testing.T) {
	t.Parallel()
	okOnce := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	}))
	t.Cleanup(okOnce.Close)
	okHTTP, err := http.Get(okOnce.URL)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = okHTTP.Body.Close() }()
	okGot := TryHTTPOnce(0, 0,
		func() (*http.Response, error) { return okHTTP, nil },
		func(string) {},
		func(code int) bool { return IsRetryableHTTPStatus(code) },
		func(*http.Response) *ProviderError { return nil },
		func(resp *http.Response) AttemptOutcome {
			return AttemptOutcome{Resp: Response{StatusCode: 200}}
		},
	)
	if okGot.Err != nil {
		t.Fatal(okGot.Err)
	}
	if okGot.Resp.StatusCode != 200 {
		t.Fatalf("status=%d", okGot.Resp.StatusCode)
	}
}

func TestTryHTTPOnceRetryableStatus(t *testing.T) {
	t.Parallel()
	errOnce := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		http.Error(w, "no", http.StatusBadGateway)
	}))
	t.Cleanup(errOnce.Close)
	errHTTP, err := http.Get(errOnce.URL)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = errHTTP.Body.Close() }()
	errGot := TryHTTPOnce(1, 0,
		func() (*http.Response, error) { return errHTTP, nil },
		func(string) {},
		func(code int) bool { return IsRetryableHTTPStatus(code) },
		func(resp *http.Response) *ProviderError {
			return ReadProviderError("t", resp, nil)
		},
		func(*http.Response) AttemptOutcome { return AttemptOutcome{} },
	)
	if errGot.Err == nil {
		t.Fatal("err")
	}
	if !errGot.Retry {
		t.Fatal("retry")
	}
}
