package ratelimit

import (
	"fmt"
	"strings"

	"github.com/redis/go-redis/v9"
)

// ParseRedisURL builds a go-redis client from a redis:// URL.
func ParseRedisURL(raw string) (redis.UniversalClient, error) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return nil, fmt.Errorf("REDIS_URL is required")
	}
	opts, err := redis.ParseURL(raw)
	if err != nil {
		return nil, fmt.Errorf("parse REDIS_URL: %w", err)
	}
	return redis.NewClient(opts), nil
}
