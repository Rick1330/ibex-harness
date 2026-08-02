package ratelimit

import (
	"context"
	"testing"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
)

func TestRedisKeyed_underAtOverLimit(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })

	limiter, err := NewRedisKeyed(client, RedisKeyedConfig{
		DefaultRPM: 3,
		KeyPrefix:  "ratelimit:auth:validate",
	})
	if err != nil {
		t.Fatalf("NewRedisKeyed: %v", err)
	}
	ctx := context.Background()
	for i := 0; i < 3; i++ {
		res, err := limiter.CheckKey(ctx, "127.0.0.1")
		if err != nil || !res.Allowed {
			t.Fatalf("request %d: allowed=%v err=%v", i+1, res.Allowed, err)
		}
	}
	res, err := limiter.CheckKey(ctx, "127.0.0.1")
	if err != nil {
		t.Fatalf("over: %v", err)
	}
	if res.Allowed {
		t.Fatal("expected deny on 4th request")
	}
	other, err := limiter.CheckKey(ctx, "10.0.0.2")
	if err != nil || !other.Allowed {
		t.Fatalf("other peer should be independent: allowed=%v err=%v", other.Allowed, err)
	}
}

func TestNewRedisKeyed_nilClient(t *testing.T) {
	t.Parallel()
	_, err := NewRedisKeyed(nil, RedisKeyedConfig{})
	if err != ErrNilClient {
		t.Fatalf("want ErrNilClient, got %v", err)
	}
}

func TestNoopKeyed_alwaysAllows(t *testing.T) {
	t.Parallel()
	res, err := NoopKeyed().CheckKey(context.Background(), "any")
	if err != nil || !res.Allowed {
		t.Fatalf("noop: allowed=%v err=%v", res.Allowed, err)
	}
}
