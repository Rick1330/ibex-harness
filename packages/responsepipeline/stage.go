package responsepipeline

import "context"

// Stage transforms a decoded non-streaming chat completion response.
type Stage interface {
	Name() string
	Process(ctx context.Context, resp *ChatResponse) (*ChatResponse, error)
}

// SecurityCriticaler marks stages that must fail closed on error (Phase 3 guardrails).
// Named per Go single-method interface convention (method SecurityCritical + -er).
type SecurityCriticaler interface {
	SecurityCritical() bool
}

// SecurityCritical is kept as a type alias for existing call sites and ADR-0044 docs.
type SecurityCritical = SecurityCriticaler
