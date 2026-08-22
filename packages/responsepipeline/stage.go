package responsepipeline

import "context"

// Stage transforms a decoded non-streaming chat completion response.
type Stage interface {
	Name() string
	Process(ctx context.Context, resp *ChatResponse) (*ChatResponse, error)
}

// SecurityCritical marks stages that must fail closed on error (Phase 3 guardrails).
type SecurityCritical interface {
	SecurityCritical() bool
}
