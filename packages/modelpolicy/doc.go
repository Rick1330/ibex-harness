// Package modelpolicy implements per-org model allow/deny policies (ADR-0075 / m4.C.2).
package modelpolicy

import (
	"errors"
	"time"
)

// ErrModelNotAllowedForOrg is returned when an org policy denies the candidate model.
var ErrModelNotAllowedForOrg = errors.New("model not allowed for this organization")

// ErrPolicyUnavailable is returned when policy load/cache infrastructure fails (fail closed).
var ErrPolicyUnavailable = errors.New("model policy unavailable")

const (
	defaultCacheTTL      = 60 * time.Second
	defaultBloomExpected = 10_000
	defaultBloomFPRate   = 0.01
	defaultLRUSize       = 4096
)

// Policy is one org_model_policies row used for evaluation.
type Policy struct {
	ID       string
	OrgID    string
	Pattern  string
	Allowed  bool
	Priority int
}

// Config holds cache sizing and TTL.
type Config struct {
	CacheTTL      time.Duration
	BloomExpected uint
	BloomFPRate   float64
	LRUSize       int
}

// ApplyDefaults fills zero-valued fields.
func (c *Config) ApplyDefaults() {
	if c.CacheTTL <= 0 {
		c.CacheTTL = defaultCacheTTL
	}
	if c.BloomExpected == 0 {
		c.BloomExpected = defaultBloomExpected
	}
	if c.BloomFPRate <= 0 || c.BloomFPRate >= 1 {
		c.BloomFPRate = defaultBloomFPRate
	}
	if c.LRUSize <= 0 {
		c.LRUSize = defaultLRUSize
	}
}
