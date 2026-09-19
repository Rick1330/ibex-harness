package billing

import "time"

const (
	defaultCacheTTL    = 60 * time.Second
	defaultLRUSize     = 4096
	defaultLoadTimeout = 200 * time.Millisecond
)

// EnforcementMode controls whether the proxy hard-denies over-budget requests.
type EnforcementMode string

const (
	EnforcementAlertOnly EnforcementMode = "alert_only"
	EnforcementHardCap   EnforcementMode = "hard_cap"
)

// Config holds cache sizing and TTL.
type Config struct {
	CacheTTL    time.Duration
	LRUSize     int
	LoadTimeout time.Duration
}

// ApplyDefaults fills zero-valued fields.
func (c *Config) ApplyDefaults() {
	if c.CacheTTL <= 0 {
		c.CacheTTL = defaultCacheTTL
	}
	if c.LRUSize <= 0 {
		c.LRUSize = defaultLRUSize
	}
	if c.LoadTimeout <= 0 {
		c.LoadTimeout = defaultLoadTimeout
	}
}
