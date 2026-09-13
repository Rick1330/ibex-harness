package provider

import (
	"context"
	"errors"
)

// Fallback reason labels for metrics / ClickHouse (ADR-0077).
const (
	FallbackReasonCircuitOpen = "provider_circuit_open"
	FallbackReason5xx         = "provider_5xx"
	FallbackReasonTimeout     = "provider_timeout"
)

// ErrUpstreamTimeout marks an upstream-side deadline that must trip breakers and
// may trigger fallback, without matching context.DeadlineExceeded (caller abandonment).
var ErrUpstreamTimeout = errors.New("upstream timed out")

// FallbackDecision is the pure eligibility outcome for provider fallback routing.
type FallbackDecision struct {
	Eligible bool
	Reason   string
}

// FallbackEligible reports whether err + request may attempt a policy fallback hop.
// BYO overrides never fallback. Client-fault 4xx (including 429) never fallback.
func FallbackEligible(err error, req Request) FallbackDecision {
	if err == nil || hasUpstreamOverride(req) {
		return FallbackDecision{}
	}
	if d, ok := fallbackFromProviderError(err); ok {
		return d
	}
	return fallbackFromTimeout(err)
}

func fallbackFromProviderError(err error) (FallbackDecision, bool) {
	var pe *ProviderError
	if !errors.As(err, &pe) || pe == nil {
		return FallbackDecision{}, false
	}
	switch {
	case pe.Reason == ErrorReasonCircuitOpen:
		return FallbackDecision{Eligible: true, Reason: FallbackReasonCircuitOpen}, true
	case pe.StatusCode >= 500:
		return FallbackDecision{Eligible: true, Reason: FallbackReason5xx}, true
	case pe.StatusCode >= 400 && pe.StatusCode < 500:
		return FallbackDecision{}, true
	default:
		return FallbackDecision{}, false
	}
}

func fallbackFromTimeout(err error) FallbackDecision {
	if errors.Is(err, ErrUpstreamTimeout) || errors.Is(err, context.DeadlineExceeded) {
		return FallbackDecision{Eligible: true, Reason: FallbackReasonTimeout}
	}
	return FallbackDecision{}
}
