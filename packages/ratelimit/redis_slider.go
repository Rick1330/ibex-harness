package ratelimit

import (
	"context"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

const keyTTL = 90 * time.Second

type minuteWindow struct {
	unixMinute int64
	resetUnix  int64
	retryAfter time.Duration
}

// RedisSliderConfig configures org-level per-minute rate limits.
type RedisSliderConfig struct {
	DefaultRPM   int64
	OrgOverrides map[uuid.UUID]int64
}

// RedisSlider implements a calendar-minute sliding window using Redis INCR + EXPIRE.
// Phase 1: org-level only; agentID is ignored.
// NOTE: INCR + EXPIRE is not atomic. Phase 4 replaces this with Lua scripts.
type RedisSlider struct {
	client redis.UniversalClient
	cfg    RedisSliderConfig
}

// NewRedisSlider returns an org-level rate limiter backed by Redis.
func NewRedisSlider(client redis.UniversalClient, cfg RedisSliderConfig) Limiter {
	if cfg.DefaultRPM < 1 {
		cfg.DefaultRPM = 60
	}
	return &RedisSlider{client: client, cfg: cfg}
}

func (r *RedisSlider) Check(ctx context.Context, orgID, _ uuid.UUID) (Result, error) {
	limit := r.effectiveLimit(orgID)
	if limit < 1 {
		limit = 60
	}

	window := currentMinuteWindow(time.Now().UTC())
	key := fmt.Sprintf("ratelimit:%s:rpm:%d", orgID.String(), window.unixMinute)

	count, err := r.incrWithExpire(ctx, key)
	if err != nil {
		return Result{}, fmt.Errorf("RedisSlider.Check orgID=%s: %w", orgID, err)
	}
	return resultFromCount(count, limit, window), nil
}

func (r *RedisSlider) incrWithExpire(ctx context.Context, key string) (int64, error) {
	count, err := r.client.Incr(ctx, key).Result()
	if err != nil {
		return 0, err
	}
	if count == 1 {
		if expireErr := r.client.Expire(ctx, key, keyTTL).Err(); expireErr != nil {
			return 0, expireErr
		}
	}
	return count, nil
}

func currentMinuteWindow(now time.Time) minuteWindow {
	unixMinute := now.Unix() / 60
	resetUnix := (unixMinute + 1) * 60
	retryAfter := time.Until(time.Unix(resetUnix, 0))
	if retryAfter < 0 {
		retryAfter = 0
	}
	return minuteWindow{unixMinute: unixMinute, resetUnix: resetUnix, retryAfter: retryAfter}
}

func resultFromCount(count, limit int64, window minuteWindow) Result {
	remaining := int(limit) - int(count)
	if remaining < 0 {
		remaining = 0
	}
	if count > limit {
		return Result{
			Allowed:    false,
			Limit:      int(limit),
			Remaining:  0,
			ResetUnix:  window.resetUnix,
			RetryAfter: window.retryAfter,
		}
	}
	return Result{
		Allowed:    true,
		Limit:      int(limit),
		Remaining:  remaining,
		ResetUnix:  window.resetUnix,
	}
}

func (r *RedisSlider) effectiveLimit(orgID uuid.UUID) int64 {
	if rpm, ok := r.cfg.OrgOverrides[orgID]; ok && rpm > 0 {
		return rpm
	}
	return r.cfg.DefaultRPM
}
