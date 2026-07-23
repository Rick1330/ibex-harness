package authcache

import (
	"context"
	"time"
)

// Result holds validated token claims suitable for caching.
type Result struct {
	OrgID       string
	Permissions int64
	AgentID     string
	UserID      string
	TokenID     string
	ExpiresAt   time.Time
	// FromCache is true when Validate served claims from the LRU without upstream.
	FromCache bool
}

// Upstream validates tokens with the authoritative auth service.
type Upstream interface {
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
