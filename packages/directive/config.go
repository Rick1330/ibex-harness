package directive

import "time"

const defaultCacheTTL = 60 * time.Second

// Config holds directive cache settings.
type Config struct {
	// CacheTTL is the Redis key TTL. Zero applies the default (60s).
	CacheTTL time.Duration
}

// ApplyDefaults fills zero-valued fields.
func (c *Config) ApplyDefaults() {
	if c.CacheTTL <= 0 {
		c.CacheTTL = defaultCacheTTL
	}
}
