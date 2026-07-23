package authcache

import (
	"fmt"
	"time"
)

const (
	defaultLRUCapacity        = 5000
	defaultLRUMaxTTL          = 30 * time.Second
	defaultBloomExpectedItems = 10000
	defaultBloomFPRate        = 0.001
	tokenExpirySkew           = 5 * time.Second
)

// Config holds in-process auth cache sizing and TTL.
type Config struct {
	LRUCapacity        int
	LRUMaxTTL          time.Duration
	BloomExpectedItems uint
	BloomFPRate        float64
}

// ApplyDefaults fills zero-valued fields with production defaults.
func (c *Config) ApplyDefaults() {
	if c.LRUCapacity < 1 {
		c.LRUCapacity = defaultLRUCapacity
	}
	if c.LRUMaxTTL <= 0 {
		c.LRUMaxTTL = defaultLRUMaxTTL
	}
	if c.BloomExpectedItems < 1 {
		c.BloomExpectedItems = defaultBloomExpectedItems
	}
	if c.BloomFPRate <= 0 || c.BloomFPRate >= 1 {
		c.BloomFPRate = defaultBloomFPRate
	}
}

// Validate checks Config after ApplyDefaults.
func (c Config) Validate() error {
	if c.LRUCapacity < 1 {
		return fmt.Errorf("authcache: LRUCapacity must be >= 1")
	}
	if c.LRUMaxTTL <= 0 {
		return fmt.Errorf("authcache: LRUMaxTTL must be positive")
	}
	if c.BloomExpectedItems < 1 {
		return fmt.Errorf("authcache: BloomExpectedItems must be >= 1")
	}
	if c.BloomFPRate <= 0 || c.BloomFPRate >= 1 {
		return fmt.Errorf("authcache: BloomFPRate must be in (0,1)")
	}
	return nil
}
