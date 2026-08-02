package ratelimit

import (
	"context"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

// RedisSliderConfig configures org-level per-minute rate limits.
type RedisSliderConfig struct {
	DefaultRPM   int64
	OrgOverrides map[uuid.UUID]int64
}

// RedisSlider implements a calendar-minute sliding window using Redis.
// Phase 1: org-level only; agentID is ignored.
// INCR+EXPIRE is atomic via shared Lua (incrWithExpire).
type RedisSlider struct {
	client redis.UniversalClient
	cfg    RedisSliderConfig
}

// NewRedisSlider returns an org-level rate limiter backed by Redis.
// client must be non-nil; the limiter has no fallback transport.
func NewRedisSlider(client redis.UniversalClient, cfg RedisSliderConfig) (Limiter, error) {
	if client == nil {
		return nil, ErrNilClient
	}
	if cfg.DefaultRPM < 1 {
		cfg.DefaultRPM = 60
	}
	return &RedisSlider{client: client, cfg: cfg}, nil
}

func (r *RedisSlider) Check(ctx context.Context, orgID, _ uuid.UUID) (Result, error) {
	limit := r.effectiveLimit(orgID)
	if limit < 1 {
		limit = 60
	}

	window := currentMinuteWindow(time.Now().UTC())
	key := fmt.Sprintf("ratelimit:%s:rpm:%d", orgID.String(), window.unixMinute)

	count, err := incrWithExpire(ctx, r.client, key)
	if err != nil {
		return Result{}, fmt.Errorf("RedisSlider.Check orgID=%s: %w", orgID.String(), err)
	}
	return resultFromCount(count, limit, window), nil
}

func (r *RedisSlider) effectiveLimit(orgID uuid.UUID) int64 {
	if rpm, ok := r.cfg.OrgOverrides[orgID]; ok && rpm > 0 {
		return rpm
	}
	return r.cfg.DefaultRPM
}
