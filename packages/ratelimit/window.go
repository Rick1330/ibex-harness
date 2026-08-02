package ratelimit

import (
	"context"
	"fmt"
	"time"

	"github.com/redis/go-redis/v9"
)

const keyTTL = 90 * time.Second

type minuteWindow struct {
	unixMinute int64
	resetUnix  int64
	retryAfter time.Duration
}

// timeNowUTC is overridden in tests.
var timeNowUTC = func() time.Time { return time.Now().UTC() }

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
		Allowed:   true,
		Limit:     int(limit),
		Remaining: remaining,
		ResetUnix: window.resetUnix,
	}
}

func incrWithExpire(ctx context.Context, client redis.UniversalClient, key string) (int64, error) {
	count, err := client.Incr(ctx, key).Result()
	if err != nil {
		return 0, err
	}
	if count == 1 {
		if expireErr := client.Expire(ctx, key, keyTTL).Err(); expireErr != nil {
			return 0, expireErr
		}
	}
	return count, nil
}

func keyedMinuteRedisKey(prefix, key string, unixMinute int64) string {
	return fmt.Sprintf("%s:%s:rpm:%d", prefix, key, unixMinute)
}
