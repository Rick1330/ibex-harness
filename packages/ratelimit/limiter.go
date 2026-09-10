package ratelimit

import (
	"context"
	"errors"
	"time"

	"github.com/google/uuid"
)

// ErrNilClient lets callers distinguish invalid limiter construction from Redis operation failures.
var ErrNilClient = errors.New("ratelimit: nil redis client")

// Limiter checks and enforces rate limits.
type Limiter interface {
	// Check checks the rate limit for the given org and agent.
	// A nil agentID skips the agent tier (org + global only).
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
	// DeniedTier is set when Allowed is false: "agent", "org", or "global".
	// Empty when Allowed is true. Internal only — not exposed as an HTTP header.
	DeniedTier string
}

type noopLimiter struct{}

func (noopLimiter) Check(_ context.Context, _, _ uuid.UUID) (Result, error) {
	return Result{Allowed: true, Limit: 0, Remaining: 0}, nil
}

// Noop returns a limiter that always allows requests (tests and disabled paths).
func Noop() Limiter {
	return noopLimiter{}
}
