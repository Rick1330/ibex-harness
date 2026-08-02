package ratelimit

import (
	"context"
	"fmt"
	"time"

	"github.com/redis/go-redis/v9"
)

const keyTTL = 90 * time.Second

// incrExpireLua atomically INCR and EXPIRE-on-create so counters never lack TTL
// if the process dies between INCR and EXPIRE (ADR-0015 race window shrink).
var incrExpireLua = redis.NewScript(`
local n = redis.call("INCR", KEYS[1])
if n == 1 then
  redis.call("EXPIRE", KEYS[1], ARGV[1])
end
return n
`)

type minuteWindow struct {
	unixMinute int64
	resetUnix  int64
	retryAfter time.Duration
}

func currentMinuteWindow(now time.Time) minuteWindow {
	unixMinute := now.Unix() / 60
	resetUnix := (unixMinute + 1) * 60
	return minuteWindow{
		unixMinute: unixMinute,
		resetUnix:  resetUnix,
		retryAfter: time.Unix(resetUnix, 0).Sub(now),
	}
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
	n, err := incrExpireLua.Run(ctx, client, []string{key}, int(keyTTL.Seconds())).Int64()
	if err != nil {
		return 0, fmt.Errorf("incrWithExpire: %w", err)
	}
	return n, nil
}

func keyedMinuteRedisKey(prefix, key string, unixMinute int64) string {
	return fmt.Sprintf("%s:%s:rpm:%d", prefix, key, unixMinute)
}
