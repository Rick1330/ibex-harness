package provider

import (
	"context"
	"errors"
	"fmt"
	"net/http"

	"github.com/Rick1330/ibex-harness/packages/circuitbreaker"
)

// ClassifyForBreaker keeps caller abandonment from tripping the breaker, while
// ensuring upstream timeouts that wrap DeadlineExceeded still count as failures.
// Client-fault 4xx (except 429) are left as ProviderError; packages/circuitbreaker
// treats them as non-failures via IsSuccessful / rolling IsExcluded (ADR-0076).
func ClassifyForBreaker(ctx context.Context, err error) error {
	switch {
	case errors.Is(ctx.Err(), context.Canceled):
		return context.Canceled
	case errors.Is(ctx.Err(), context.DeadlineExceeded):
		return context.DeadlineExceeded
	case errors.Is(err, context.DeadlineExceeded):
		// Do not wrap with %w: errors.Is must not match DeadlineExceeded.
		return fmt.Errorf("upstream timed out: %v", err)
	default:
		return err
	}
}

// DecodeBreakerResult unwraps a circuitbreaker Execute result into Response.
func DecodeBreakerResult(name string, out any, err error) (Response, error) {
	if err != nil {
		return MapBreakerError(name, err)
	}
	resp, ok := out.(Response)
	if !ok {
		return Response{}, fmt.Errorf("%s: circuit breaker returned unexpected result", name)
	}
	return resp, nil
}

// MapBreakerError maps circuitbreaker.ErrOpen / OpenError to ProviderError.
func MapBreakerError(name string, err error) (Response, error) {
	var pe *ProviderError
	if errors.As(err, &pe) {
		return Response{}, pe
	}
	if errors.Is(err, circuitbreaker.ErrOpen) {
		out := &ProviderError{
			ProviderName:   name,
			StatusCode:     http.StatusServiceUnavailable,
			ProviderErrMsg: "circuit breaker open",
			Reason:         ErrorReasonCircuitOpen,
		}
		var oe *circuitbreaker.OpenError
		if errors.As(err, &oe) && oe != nil {
			out.RetryAfter = oe.RetryAfter
		}
		return Response{}, out
	}
	return Response{}, err
}
