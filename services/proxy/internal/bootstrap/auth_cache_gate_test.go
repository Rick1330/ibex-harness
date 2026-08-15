package bootstrap

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
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

func closedTestRedisClient(t *testing.T) *redis.Client {
	t.Helper()
	// Unreachable address forces Ping failure without sharing miniredis lifecycle.
	dead := redis.NewClient(&redis.Options{Addr: "127.0.0.1:1"})
	t.Cleanup(func() { _ = dead.Close() })
	return dead
}

func TestUnit_MaybeWrapAuthCache(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name    string
		cfg     config.Config
		redis   func(t *testing.T) redis.UniversalClient
		wantHit bool
	}{
		{
			name:    "disabled",
			cfg:     config.Config{AuthCache: config.AuthCacheConfig{Enabled: false}},
			redis:   func(t *testing.T) redis.UniversalClient { return nil },
			wantHit: false,
		},
		{
			name:    "nil_redis",
			cfg:     config.Config{AuthCache: validAuthCacheConfig()},
			redis:   func(t *testing.T) redis.UniversalClient { return nil },
			wantHit: false,
		},
		{
			name:    "ping_fails",
			cfg:     config.Config{AuthCache: validAuthCacheConfig()},
			redis:   func(t *testing.T) redis.UniversalClient { return closedTestRedisClient(t) },
			wantHit: false,
		},
		{
			name:    "healthy_wrap",
			cfg:     config.Config{AuthCache: validAuthCacheConfig()},
			redis:   func(t *testing.T) redis.UniversalClient { return testRedisClient(t) },
			wantHit: true,
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
			if tc.wantHit {
				assertCachingValidator(t, got)
				return
			}
			assertNotCachingValidator(t, got)
			if got != inner {
				t.Fatal("expected unwrapped validator")
			}
		})
	}
}

func TestUnit_AuthCacheUnavailableReason(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name       string
		client     func(t *testing.T) redis.UniversalClient
		wantReason string
		wantErr    bool
	}{
		{
			name:       "nil",
			client:     func(t *testing.T) redis.UniversalClient { return nil },
			wantReason: "redis_url_empty",
		},
		{
			name:       "healthy",
			client:     func(t *testing.T) redis.UniversalClient { return testRedisClient(t) },
			wantReason: "",
		},
		{
			name:       "unreachable",
			client:     func(t *testing.T) redis.UniversalClient { return closedTestRedisClient(t) },
			wantReason: "redis_ping_failed",
			wantErr:    true,
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			reason, err := authCacheUnavailableReason(tc.client(t))
			if reason != tc.wantReason {
				t.Fatalf("reason=%q want %q", reason, tc.wantReason)
			}
			if tc.wantErr && err == nil {
				t.Fatal("expected ping error")
			}
			if !tc.wantErr && err != nil {
				t.Fatalf("unexpected err=%v", err)
			}
		})
	}
}
