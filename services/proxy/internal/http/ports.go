package http

import (
	"context"

	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
)

// TokenValidator is the HTTP consumer port for bearer validation.
// Concrete adapters live in services/proxy/internal/auth (gRPC + cache wrap).
type TokenValidator interface {
	Validate(ctx context.Context, accessToken string) (*auth.ValidateResult, error)
}

// AgentVerifier is the HTTP consumer port for agent ownership checks.
// Concrete adapters live in services/proxy/internal/auth.
type AgentVerifier interface {
	Verify(ctx context.Context, bearer, agentID, orgID string) (*auth.AgentRecord, error)
}
