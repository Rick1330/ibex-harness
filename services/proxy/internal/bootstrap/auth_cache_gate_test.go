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

func gateDeps(redisClient redis.UniversalClient) authCacheDeps {
	return authCacheDeps{log: logger.Discard("proxy"), redisClient: redisClient}
}

func TestUnit_MaybeWrapAuthCache_SkipCases(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name  string
		cfg   config.Config
		redis func(t *testing.T) redis.UniversalClient
	}{
		{
			name:  "disabled",
			cfg:   config.Config{AuthCache: config.AuthCacheConfig{Enabled: false}},
			redis: func(t *testing.T) redis.UniversalClient { return nil },
		},
		{
			name:  "nil_redis",
			cfg:   config.Config{AuthCache: validAuthCacheConfig()},
			redis: func(t *testing.T) redis.UniversalClient { return nil },
		},
		{
			name: "ping_fails",
			cfg:  config.Config{AuthCache: validAuthCacheConfig()},
			redis: func(t *testing.T) redis.UniversalClient {
				t.Helper()
				mr := miniredis.RunT(t)
				client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
				t.Cleanup(func() { _ = client.Close() })
				mr.Close()
				return client
			},
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			inner := stubValidator{}
			got, err := maybeWrapAuthCache(inner, tc.cfg, gateDeps(tc.redis(t)))
			if err != nil {
				t.Fatalf("err=%v", err)
			}
			assertNotCachingValidator(t, got)
			if got != inner {
				t.Fatal("expected unwrapped validator")
			}
		})
	}
}

func TestUnit_MaybeWrapAuthCache_WrapsWhenRedisHealthy(t *testing.T) {
	t.Parallel()

	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })

	inner := stubValidator{}
	cfg := config.Config{AuthCache: validAuthCacheConfig()}

	got, err := maybeWrapAuthCache(inner, cfg, gateDeps(client))

	if err != nil {
		t.Fatalf("err=%v", err)
	}
	assertCachingValidator(t, got)
}

func TestUnit_AuthCacheUnavailableReason(t *testing.T) {
	t.Parallel()

	reason, err := authCacheUnavailableReason(nil)
	if reason != "redis_url_empty" || err != nil {
		t.Fatalf("nil client reason=%q err=%v", reason, err)
	}

	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	reason, err = authCacheUnavailableReason(client)
	if reason != "" || err != nil {
		t.Fatalf("healthy redis reason=%q err=%v", reason, err)
	}

	mr.Close()
	reason, err = authCacheUnavailableReason(client)
	if reason != "redis_ping_failed" || err == nil {
		t.Fatalf("closed redis reason=%q err=%v", reason, err)
	}
}
