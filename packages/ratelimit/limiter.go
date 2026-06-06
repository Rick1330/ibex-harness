package ratelimit

import (
	"context"
	"time"

	"github.com/google/uuid"
)

// Limiter checks and enforces rate limits.
// Phase 4 will add hierarchical Lua-based limits without changing callers.
type Limiter interface {
	// Check checks the rate limit for the given org and agent.
	// agentID is reserved for Phase 4 agent-level limits; Phase 1 uses org-level only.
	// Returns Result and a non-nil error only for infrastructure failures (Redis down, etc.).
	Check(ctx context.Context, orgID, agentID uuid.UUID) (Result, error)
}

// Result is the outcome of a rate limit check.
type Result struct {
	Allowed    bool
	Limit      int
	Remaining  int
	ResetUnix  int64
	RetryAfter time.Duration
}

type noopLimiter struct{}

func (noopLimiter) Check(_ context.Context, _, _ uuid.UUID) (Result, error) {
	return Result{Allowed: true, Limit: 0, Remaining: 0}, nil
}

// Noop returns a limiter that always allows requests (tests and disabled paths).
func Noop() Limiter {
	return noopLimiter{}
}
