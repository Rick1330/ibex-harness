package provider

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/circuitbreaker"
)

func TestClassifyForBreaker_CallerVsUpstreamDeadline(t *testing.T) {
	t.Parallel()
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if !errors.Is(ClassifyForBreaker(ctx, context.Canceled), context.Canceled) {
		t.Fatal("canceled")
	}

	dead, cancelDead := context.WithTimeout(context.Background(), time.Nanosecond)
	defer cancelDead()
	<-dead.Done()
	if !errors.Is(ClassifyForBreaker(dead, context.DeadlineExceeded), context.DeadlineExceeded) {
		t.Fatal("caller deadline")
	}

	up := ClassifyForBreaker(context.Background(), context.DeadlineExceeded)
	if errors.Is(up, context.DeadlineExceeded) {
		t.Fatal("upstream deadline must not match DeadlineExceeded")
	}
	if !strings.Contains(up.Error(), "upstream timed out") {
		t.Fatalf("up=%v", up)
	}
}

func TestMapBreakerError_OpenRetryAfter(t *testing.T) {
	t.Parallel()
	_, err := MapBreakerError("openai", &circuitbreaker.OpenError{RetryAfter: 30 * time.Second})
	var pe *ProviderError
	if !errors.As(err, &pe) {
		t.Fatalf("err=%v", err)
	}
	if pe.Reason != ErrorReasonCircuitOpen {
		t.Fatalf("Reason=%q", pe.Reason)
	}
	if pe.RetryAfter != 30*time.Second {
		t.Fatalf("RetryAfter=%v", pe.RetryAfter)
	}
}

func TestCompleteWithBreaker_NilPassthrough(t *testing.T) {
	t.Parallel()
	want := Response{StatusCode: 200, ProviderRequestID: "rid"}
	got, err := CompleteWithBreaker(context.Background(), BreakerComplete{
		Name: "x",
		Once: func(context.Context, Request) (Response, error) { return want, nil },
	}, Request{Model: "m"})
	if err != nil {
		t.Fatalf("err=%v", err)
	}
	if got.StatusCode != want.StatusCode {
		t.Fatalf("StatusCode=%d", got.StatusCode)
	}
	if got.ProviderRequestID != want.ProviderRequestID {
		t.Fatalf("ProviderRequestID=%q", got.ProviderRequestID)
	}
}

func TestCompleteWithBreaker_OpenMapsRetryAfter(t *testing.T) {
	t.Parallel()
	cool := 12 * time.Second
	br, err := circuitbreaker.New(circuitbreaker.Settings{Name: "cwb", MaxFailures: 1, CoolDown: cool})
	if err != nil {
		t.Fatal(err)
	}
	_, _ = br.Execute(func() (any, error) { return nil, errors.New("fail") })
	_, err = CompleteWithBreaker(context.Background(), BreakerComplete{
		Breaker: br,
		Name:    "openai",
		Once: func(context.Context, Request) (Response, error) {
			return Response{}, nil
		},
	}, Request{})
	assertCircuitOpenPE(t, err, cool)
}

func assertCircuitOpenPE(t *testing.T, err error, cool time.Duration) {
	t.Helper()
	var pe *ProviderError
	if !errors.As(err, &pe) {
		t.Fatalf("err=%v", err)
	}
	if pe.Reason != ErrorReasonCircuitOpen {
		t.Fatalf("Reason=%q", pe.Reason)
	}
	if pe.RetryAfter != cool {
		t.Fatalf("RetryAfter=%v", pe.RetryAfter)
	}
}

func TestCompleteWithBreaker_BypassesSharedBreakerOnOverride(t *testing.T) {
	t.Parallel()
	br := openBreaker(t, "byo", time.Minute)
	assertOverrideBypasses(t, br, Request{APIKeyOverride: "sk-byo"}, "byo")
	assertOverrideBypasses(t, br, Request{BaseURLOverride: "https://byo.example/v1"}, "url")
}

func openBreaker(t *testing.T, name string, cool time.Duration) *circuitbreaker.Breaker {
	t.Helper()
	br, err := circuitbreaker.New(circuitbreaker.Settings{Name: name, MaxFailures: 1, CoolDown: cool})
	if err != nil {
		t.Fatal(err)
	}
	_, _ = br.Execute(func() (any, error) { return nil, errors.New("fail") })
	if br.State() != "open" {
		t.Fatalf("state=%s", br.State())
	}
	return br
}

func assertOverrideBypasses(t *testing.T, br *circuitbreaker.Breaker, req Request, wantID string) {
	t.Helper()
	got, err := CompleteWithBreaker(context.Background(), BreakerComplete{
		Breaker: br,
		Name:    "openai",
		Once: func(context.Context, Request) (Response, error) {
			return Response{StatusCode: 200, ProviderRequestID: wantID}, nil
		},
	}, req)
	if err != nil {
		t.Fatalf("err=%v", err)
	}
	if got.ProviderRequestID != wantID {
		t.Fatalf("ProviderRequestID=%q want %q", got.ProviderRequestID, wantID)
	}
}

func TestDecodeBreakerResult_InvalidTypeAndPassthrough(t *testing.T) {
	t.Parallel()
	_, err := DecodeBreakerResult("openai", "nope", nil)
	if err == nil {
		t.Fatal("want unexpected result error")
	}
	if !strings.Contains(err.Error(), "unexpected result") {
		t.Fatalf("err=%v", err)
	}
	_, err = MapBreakerError("openai", errors.New("transport"))
	if err == nil {
		t.Fatal("want transport error")
	}
	if err.Error() != "transport" {
		t.Fatalf("passthrough err=%v", err)
	}
	_, err = MapBreakerError("openai", circuitbreaker.ErrOpen)
	assertCircuitOpenPE(t, err, 0)
}

func TestProviderError_HTTPStatusNilSafe(t *testing.T) {
	t.Parallel()
	if (*ProviderError)(nil).HTTPStatus() != 0 {
		t.Fatal("nil HTTPStatus")
	}
	pe := &ProviderError{StatusCode: 429}
	if pe.HTTPStatus() != 429 {
		t.Fatalf("got %d", pe.HTTPStatus())
	}
}
