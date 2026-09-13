package provider

import (
	"context"
	"errors"
	"net/http"
	"testing"
)

func TestFallbackEligible_CircuitOpenAnd5xx(t *testing.T) {
	t.Parallel()
	req := Request{Model: "gpt-4o"}
	open := FallbackEligible(&ProviderError{
		ProviderName: "openai",
		StatusCode:   http.StatusServiceUnavailable,
		Reason:       ErrorReasonCircuitOpen,
	}, req)
	if !open.Eligible || open.Reason != FallbackReasonCircuitOpen {
		t.Fatalf("circuit: %+v", open)
	}
	five := FallbackEligible(&ProviderError{
		ProviderName: "openai", StatusCode: http.StatusBadGateway,
	}, req)
	if !five.Eligible || five.Reason != FallbackReason5xx {
		t.Fatalf("5xx: %+v", five)
	}
}

func TestFallbackEligible_Never4xxIncluding429(t *testing.T) {
	t.Parallel()
	req := Request{Model: "m"}
	for _, code := range []int{400, 401, 403, 404, 429} {
		got := FallbackEligible(&ProviderError{StatusCode: code}, req)
		if got.Eligible {
			t.Fatalf("status %d must not be eligible: %+v", code, got)
		}
	}
}

func TestFallbackEligible_TimeoutAndBYO(t *testing.T) {
	t.Parallel()
	req := Request{Model: "m"}
	up := FallbackEligible(ErrUpstreamTimeout, req)
	if !up.Eligible || up.Reason != FallbackReasonTimeout {
		t.Fatalf("upstream: %+v", up)
	}
	wrapped := FallbackEligible(errors.Join(ErrUpstreamTimeout, errors.New("dial")), req)
	if !wrapped.Eligible || wrapped.Reason != FallbackReasonTimeout {
		t.Fatalf("wrapped: %+v", wrapped)
	}
	dead := FallbackEligible(context.DeadlineExceeded, req)
	if !dead.Eligible || dead.Reason != FallbackReasonTimeout {
		t.Fatalf("deadline: %+v", dead)
	}
	byoKey := FallbackEligible(ErrUpstreamTimeout, Request{APIKeyOverride: "sk"})
	if byoKey.Eligible {
		t.Fatal("BYO key must not fallback")
	}
	byoURL := FallbackEligible(&ProviderError{StatusCode: 503}, Request{BaseURLOverride: "https://byo"})
	if byoURL.Eligible {
		t.Fatal("BYO URL must not fallback")
	}
	if FallbackEligible(nil, req).Eligible {
		t.Fatal("nil err")
	}
	if FallbackEligible(errors.New("transport"), req).Eligible {
		t.Fatal("generic transport not eligible")
	}
}
