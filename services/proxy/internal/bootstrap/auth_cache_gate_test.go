package bootstrap

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
)

type stubValidator struct{}

func (stubValidator) Validate(context.Context, string) (*auth.ValidateResult, error) {
	return nil, errors.New("unused")
}

func validAuthCacheConfig() config.AuthCacheConfig {
	return config.AuthCacheConfig{
		Enabled:            true,
		LRUCapacity:        100,
		LRUMaxTTL:          30 * time.Second,
		BloomExpectedItems: 1000,
		BloomFPRate:        0.001,
	}
}

func TestUnit_MaybeWrapAuthCache_Disabled(t *testing.T) {
	t.Parallel()

	inner := stubValidator{}
	cfg := config.Config{AuthCache: config.AuthCacheConfig{Enabled: false}}

	got, err := maybeWrapAuthCache(inner, cfg, logger.Discard("proxy"), nil, nil)

	if err != nil {
		t.Fatalf("err=%v", err)
	}
	if _, ok := got.(auth.CacheInvalidator); ok {
		t.Fatal("disabled cache must not wrap")
	}
	if got != inner {
		t.Fatal("expected unwrapped validator")
	}
}

func TestUnit_MaybeWrapAuthCache_SkipsWhenRedisNil(t *testing.T) {
	t.Parallel()

	inner := stubValidator{}
	cfg := config.Config{AuthCache: validAuthCacheConfig()}

	got, err := maybeWrapAuthCache(inner, cfg, logger.Discard("proxy"), nil, nil)

	if err != nil {
		t.Fatalf("err=%v", err)
	}
	if _, ok := got.(auth.CacheInvalidator); ok {
		t.Fatal("nil Redis must not wrap auth cache")
	}
	if got != inner {
		t.Fatal("expected unwrapped validator")
	}
}

func TestUnit_MaybeWrapAuthCache_SkipsWhenPingFails(t *testing.T) {
	t.Parallel()

	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	mr.Close()

	inner := stubValidator{}
	cfg := config.Config{AuthCache: validAuthCacheConfig()}

	got, err := maybeWrapAuthCache(inner, cfg, logger.Discard("proxy"), nil, client)

	if err != nil {
		t.Fatalf("err=%v", err)
	}
	if _, ok := got.(auth.CacheInvalidator); ok {
		t.Fatal("unreachable Redis must not wrap auth cache")
	}
	if got != inner {
		t.Fatal("expected unwrapped validator")
	}
}

func TestUnit_MaybeWrapAuthCache_WrapsWhenRedisHealthy(t *testing.T) {
	t.Parallel()

	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })

	inner := stubValidator{}
	cfg := config.Config{AuthCache: validAuthCacheConfig()}

	got, err := maybeWrapAuthCache(inner, cfg, logger.Discard("proxy"), nil, client)

	if err != nil {
		t.Fatalf("err=%v", err)
	}
	assertCachingValidator(t, got)
}

func TestUnit_AuthCacheSkipReason(t *testing.T) {
	t.Parallel()

	if got := authCacheSkipReason(nil); got != "redis_url_empty" {
		t.Fatalf("nil client reason=%q", got)
	}

	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	if got := authCacheSkipReason(client); got != "" {
		t.Fatalf("healthy redis reason=%q", got)
	}

	mr.Close()
	if got := authCacheSkipReason(client); got != "redis_ping_failed" {
		t.Fatalf("closed redis reason=%q", got)
	}
}
