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
	var pe *ProviderError
	if errors.As(err, &pe) && pe != nil {
		if pe.Reason == ErrorReasonCircuitOpen {
			return FallbackDecision{Eligible: true, Reason: FallbackReasonCircuitOpen}
		}
		if pe.StatusCode >= 500 {
			return FallbackDecision{Eligible: true, Reason: FallbackReason5xx}
		}
		if pe.StatusCode >= 400 && pe.StatusCode < 500 {
			return FallbackDecision{}
		}
	}
	if errors.Is(err, ErrUpstreamTimeout) {
		return FallbackDecision{Eligible: true, Reason: FallbackReasonTimeout}
	}
	if errors.Is(err, context.DeadlineExceeded) {
		return FallbackDecision{Eligible: true, Reason: FallbackReasonTimeout}
	}
	return FallbackDecision{}
}
