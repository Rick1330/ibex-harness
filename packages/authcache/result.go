package authcache

import (
	"context"
	"time"

	"github.com/google/uuid"
)

// Result holds validated token claims suitable for caching.
type Result struct {
	OrgID       uuid.UUID
	Permissions int64
	AgentID     uuid.UUID
	UserID      string
	TokenID     string
	ExpiresAt   time.Time
	// FromCache is true when Validate served claims from the LRU without upstream.
	FromCache bool
}

// Validator validates tokens with the authoritative auth service.
type Validator interface {
	Validate(ctx context.Context, accessToken string) (*Result, error)
}

func cloneResult(in *Result, fromCache bool) *Result {
	if in == nil {
		return nil
	}
	out := *in
	out.FromCache = fromCache
	return &out
}
