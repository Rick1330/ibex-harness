package ratelimit

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
)

func TestUnit_RedisKeyed_underAtOverLimit(t *testing.T) {
	t.Parallel()
	limiter := newTestKeyed(t, RedisKeyedConfig{DefaultRPM: 3, KeyPrefix: "ratelimit:auth:validate"})
	assertKeyedAllowedN(t, limiter, "127.0.0.1", 3)
	assertKeyedAllowed(t, limiter, "127.0.0.1", false)
	assertKeyedAllowed(t, limiter, "10.0.0.2", true)
}

func TestUnit_RedisKeyed_emptyKeyUsesUnknown(t *testing.T) {
	t.Parallel()
	limiter := newTestKeyed(t, RedisKeyedConfig{DefaultRPM: 1})
	assertKeyedAllowed(t, limiter, "", true)
	assertKeyedAllowed(t, limiter, "", false)
	assertKeyedAllowed(t, limiter, "unknown", false)
}

func TestUnit_RedisKeyed_setsTTLOnCreate(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	limiter, err := NewRedisKeyed(client, RedisKeyedConfig{DefaultRPM: 10, KeyPrefix: "ratelimit:ttl"})
	if err != nil {
		t.Fatalf("NewRedisKeyed: %v", err)
	}
	if _, err := limiter.CheckKey(context.Background(), "peer-a"); err != nil {
		t.Fatal(err)
	}
	keys := mr.Keys()
	if len(keys) != 1 {
		t.Fatalf("want 1 redis key, got %v", keys)
	}
	ttl := mr.TTL(keys[0])
	if ttl <= 0 || ttl > keyTTL {
		t.Fatalf("want positive TTL <= %v, got %v", keyTTL, ttl)
	}
}

func TestUnit_NewRedisKeyed_nilClient(t *testing.T) {
	t.Parallel()
	_, err := NewRedisKeyed(nil, RedisKeyedConfig{})
	if !errors.Is(err, ErrNilClient) {
		t.Fatalf("want ErrNilClient, got %v", err)
	}
}

func TestUnit_NewRedisKeyed_defaults(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	limiter, err := NewRedisKeyed(client, RedisKeyedConfig{})
	if err != nil {
		t.Fatal(err)
	}
	rk, ok := limiter.(*RedisKeyed)
	if !ok {
		t.Fatalf("want *RedisKeyed, got %T", limiter)
	}
	if rk.cfg.DefaultRPM != 6000 || rk.cfg.KeyPrefix != "ratelimit:keyed" {
		t.Fatalf("defaults: %+v", rk.cfg)
	}
	if rk.cfg.OpTimeout != DefaultRedisOpTimeout {
		t.Fatalf("OpTimeout=%v", rk.cfg.OpTimeout)
	}
}

func TestUnit_RedisKeyed_ConcurrentBurst(t *testing.T) {
	t.Parallel()
	// OpTimeout must exceed DefaultRedisOpTimeout: 80 parallel Lua scripts on
	// miniredis can exceed 50ms under CI load (coverage/race jobs).
	limiter := newTestKeyed(t, RedisKeyedConfig{
		DefaultRPM: 20,
		KeyPrefix:  "ratelimit:keyed:burst",
		OpTimeout:  time.Second,
	})
	allowed := countKeyedAllowed(burstKeyedCheck(t, limiter, "same-peer", 80))
	if allowed > 20 || allowed < 1 {
		t.Fatalf("admitted %d want 1..20", allowed)
	}
}

func TestUnit_NoopKeyed_alwaysAllows(t *testing.T) {
	t.Parallel()
	res, err := NoopKeyed().CheckKey(context.Background(), "any")
	if err != nil || !res.Allowed {
		t.Fatalf("noop: allowed=%v err=%v", res.Allowed, err)
	}
}

func TestUnit_currentMinuteWindow_retryAfterNonNegative(t *testing.T) {
	t.Parallel()
	now := time.Date(2026, 8, 2, 12, 0, 30, 0, time.UTC)
	w := currentMinuteWindow(now)
	if w.retryAfter != 30*time.Second {
		t.Fatalf("retryAfter=%v want 30s", w.retryAfter)
	}
	if w.resetUnix != now.Unix()+30 {
		t.Fatalf("resetUnix=%d", w.resetUnix)
	}
}

func burstKeyedCheck(t *testing.T, limiter KeyedLimiter, key string, n int) []Result {
	t.Helper()
	results := make([]Result, n)
	errs := make([]error, n)
	var wg sync.WaitGroup
	wg.Add(n)
	for i := 0; i < n; i++ {
		i := i
		go func() {
			defer wg.Done()
			res, err := limiter.CheckKey(context.Background(), key)
			results[i] = res
			errs[i] = err
		}()
	}
	wg.Wait()
	for i, err := range errs {
		if err != nil {
			t.Fatalf("CheckKey[%d]: %v", i, err)
		}
	}
	return results
}

func countKeyedAllowed(results []Result) int {
	n := 0
	for _, res := range results {
		if res.Allowed {
			n++
		}
	}
	return n
}

func newTestKeyed(t testing.TB, cfg RedisKeyedConfig) KeyedLimiter {
	t.Helper()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	limiter, err := NewRedisKeyed(client, cfg)
	if err != nil {
		t.Fatalf("NewRedisKeyed: %v", err)
	}
	return limiter
}

func assertKeyedAllowedN(t *testing.T, limiter KeyedLimiter, key string, n int) {
	t.Helper()
	for i := 0; i < n; i++ {
		assertKeyedAllowed(t, limiter, key, true)
	}
}

func assertKeyedAllowed(t *testing.T, limiter KeyedLimiter, key string, want bool) {
	t.Helper()
	res, err := limiter.CheckKey(context.Background(), key)
	if err != nil {
		t.Fatalf("CheckKey(%q): %v", key, err)
	}
	if res.Allowed != want {
		t.Fatalf("CheckKey(%q): allowed=%v want %v", key, res.Allowed, want)
	}
}
