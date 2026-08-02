package ratelimit

import (
	"context"
	"fmt"

	"github.com/redis/go-redis/v9"
)

// KeyedLimiter rate-limits by an opaque string key (peer address, etc.).
type KeyedLimiter interface {
	CheckKey(ctx context.Context, key string) (Result, error)
}

type noopKeyedLimiter struct{}

func (noopKeyedLimiter) CheckKey(_ context.Context, _ string) (Result, error) {
	return Result{Allowed: true, Limit: 0, Remaining: 0}, nil
}

// NoopKeyed returns a keyed limiter that always allows (tests / Redis unset).
func NoopKeyed() KeyedLimiter {
	return noopKeyedLimiter{}
}

// RedisKeyedConfig configures per-key calendar-minute limits.
type RedisKeyedConfig struct {
	DefaultRPM int64
	// KeyPrefix is the Redis key namespace, e.g. "ratelimit:auth:validate".
	KeyPrefix string
}

// RedisKeyed implements KeyedLimiter with INCR + EXPIRE (same race window as RedisSlider).
type RedisKeyed struct {
	client redis.UniversalClient
	cfg    RedisKeyedConfig
}

// NewRedisKeyed returns a keyed minute-window limiter.
func NewRedisKeyed(client redis.UniversalClient, cfg RedisKeyedConfig) (KeyedLimiter, error) {
	if client == nil {
		return nil, ErrNilClient
	}
	if cfg.DefaultRPM < 1 {
		cfg.DefaultRPM = 6000
	}
	if cfg.KeyPrefix == "" {
		cfg.KeyPrefix = "ratelimit:keyed"
	}
	return &RedisKeyed{client: client, cfg: cfg}, nil
}

// CheckKey enforces the configured RPM for key within the current UTC minute.
func (r *RedisKeyed) CheckKey(ctx context.Context, key string) (Result, error) {
	if key == "" {
		key = "unknown"
	}
	window := currentMinuteWindow(timeNowUTC())
	redisKey := keyedMinuteRedisKey(r.cfg.KeyPrefix, key, window.unixMinute)
	count, err := incrWithExpire(ctx, r.client, redisKey)
	if err != nil {
		return Result{}, fmt.Errorf("RedisKeyed.CheckKey key=%s: %w", key, err)
	}
	return resultFromCount(count, r.cfg.DefaultRPM, window), nil
}
