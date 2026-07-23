package ratelimit

import (
	"context"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

func TestRedisSlider_underAtOverLimit(t *testing.T) {
	t.Parallel()

	testOrgID := uuid.MustParse("550e8400-e29b-41d4-a716-446655440000")

	tests := []struct {
		name        string
		requests    int
		limit       int64
		wantAllowed bool
		wantRemain  int
	}{
		{name: "under limit", requests: 10, limit: 60, wantAllowed: true, wantRemain: 50},
		{name: "at limit", requests: 60, limit: 60, wantAllowed: true, wantRemain: 0},
		{name: "over limit", requests: 61, limit: 60, wantAllowed: false, wantRemain: 0},
	}

	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			mr := miniredis.RunT(t)
			client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
			t.Cleanup(func() { _ = client.Close() })

			slider := NewRedisSlider(client, RedisSliderConfig{DefaultRPM: tc.limit})
			var result Result
			var err error
			for i := 0; i < tc.requests; i++ {
				result, err = slider.Check(context.Background(), testOrgID, uuid.Nil)
				if err != nil {
					t.Fatalf("Check: %v", err)
				}
			}
			if result.Allowed != tc.wantAllowed {
				t.Errorf("Allowed = %v, want %v", result.Allowed, tc.wantAllowed)
			}
			if result.Remaining != tc.wantRemain {
				t.Errorf("Remaining = %d, want %d", result.Remaining, tc.wantRemain)
			}
			if result.Limit != int(tc.limit) {
				t.Errorf("Limit = %d, want %d", result.Limit, tc.limit)
			}
			if result.ResetUnix <= 0 {
				t.Error("ResetUnix should be positive")
			}
		})
	}
}

func TestRedisSlider_orgOverride(t *testing.T) {
	t.Parallel()

	orgA := uuid.MustParse("550e8400-e29b-41d4-a716-446655440001")
	orgB := uuid.MustParse("550e8400-e29b-41d4-a716-446655440002")

	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })

	slider := NewRedisSlider(client, RedisSliderConfig{
		DefaultRPM: 60,
		OrgOverrides: map[uuid.UUID]int64{
			orgA: 2,
		},
	})

	for i := 0; i < 2; i++ {
		res, err := slider.Check(context.Background(), orgA, uuid.Nil)
		if err != nil {
			t.Fatalf("Check orgA: %v", err)
		}
		if !res.Allowed {
			t.Fatalf("request %d should be allowed", i+1)
		}
	}
	res, err := slider.Check(context.Background(), orgA, uuid.Nil)
	if err != nil {
		t.Fatalf("Check orgA third: %v", err)
	}
	if res.Allowed {
		t.Fatal("third request for orgA should be denied")
	}

	res, err = slider.Check(context.Background(), orgB, uuid.Nil)
	if err != nil {
		t.Fatalf("Check orgB: %v", err)
	}
	if !res.Allowed {
		t.Fatal("orgB should use default limit and remain allowed")
	}
}

func TestNewRedisSlider_defaultRPMWhenZero(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	slider := NewRedisSlider(redis.NewClient(&redis.Options{Addr: mr.Addr()}), RedisSliderConfig{DefaultRPM: 0})
	res, err := slider.Check(context.Background(), uuid.MustParse("550e8400-e29b-41d4-a716-446655440000"), uuid.Nil)
	if err != nil {
		t.Fatal(err)
	}
	if !res.Allowed || res.Limit != 60 {
		t.Fatalf("result: %+v", res)
	}
}

func TestRedisSlider_Check_redisError(t *testing.T) {
	t.Parallel()
	// Use an unreachable address instead of closing miniredis: Close()+Check can
	// race under -race in CI and occasionally return a nil error.
	client := redis.NewClient(&redis.Options{
		Addr:         "127.0.0.1:1",
		DialTimeout:  50 * time.Millisecond,
		ReadTimeout:  50 * time.Millisecond,
		WriteTimeout: 50 * time.Millisecond,
		MaxRetries:   0,
	})
	t.Cleanup(func() { _ = client.Close() })

	slider := NewRedisSlider(client, RedisSliderConfig{DefaultRPM: 60})
	_, err := slider.Check(context.Background(), uuid.MustParse("550e8400-e29b-41d4-a716-446655440000"), uuid.Nil)
	if err == nil {
		t.Fatal("expected redis infrastructure error")
	}
}

func TestRedisSlider_orgOverrideZeroUsesDefault(t *testing.T) {
	t.Parallel()
	orgID := uuid.MustParse("550e8400-e29b-41d4-a716-446655440003")
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })

	slider := NewRedisSlider(client, RedisSliderConfig{
		DefaultRPM:   60,
		OrgOverrides: map[uuid.UUID]int64{orgID: 0},
	})
	res, err := slider.Check(context.Background(), orgID, uuid.Nil)
	if err != nil {
		t.Fatal(err)
	}
	if !res.Allowed || res.Limit != 60 {
		t.Fatalf("result: %+v", res)
	}
}

func TestNoop_alwaysAllows(t *testing.T) {
	t.Parallel()

	res, err := Noop().Check(context.Background(), uuid.New(), uuid.Nil)
	if err != nil {
		t.Fatal(err)
	}
	if !res.Allowed {
		t.Fatal("noop should allow")
	}
}
