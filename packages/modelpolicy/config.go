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
	defaultCacheTTL         = 60 * time.Second
	defaultLRUSize          = 4096
	defaultAgentDefaultsTTL = 30 * time.Second
	defaultAgentDefaultsLRU = 4096
	defaultLoadTimeout      = 200 * time.Millisecond
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
	CacheTTL         time.Duration
	LRUSize          int
	AgentDefaultsTTL time.Duration
	AgentDefaultsLRU int
	LoadTimeout      time.Duration
}

// ApplyDefaults fills zero-valued fields.
func (c *Config) ApplyDefaults() {
	if c.CacheTTL <= 0 {
		c.CacheTTL = defaultCacheTTL
	}
	if c.LRUSize <= 0 {
		c.LRUSize = defaultLRUSize
	}
	if c.AgentDefaultsTTL <= 0 {
		c.AgentDefaultsTTL = defaultAgentDefaultsTTL
	}
	if c.AgentDefaultsLRU <= 0 {
		c.AgentDefaultsLRU = defaultAgentDefaultsLRU
	}
	if c.LoadTimeout <= 0 {
		c.LoadTimeout = defaultLoadTimeout
	}
}
