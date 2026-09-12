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
	if pe.Reason != ErrorReasonCircuitOpen || pe.RetryAfter != 30*time.Second {
		t.Fatalf("pe=%+v", pe)
	}
}
