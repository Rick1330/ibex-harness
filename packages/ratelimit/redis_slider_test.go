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
			slider := newTestSlider(t, RedisSliderConfig{DefaultRPM: tc.limit})
			result := checkN(t, slider, testOrgID, tc.requests)
			assertLimitResult(t, result, tc.wantAllowed, tc.wantRemain, tc.limit)
		})
	}
}

func TestRedisSlider_orgOverride(t *testing.T) {
	t.Parallel()

	orgA := uuid.MustParse("550e8400-e29b-41d4-a716-446655440001")
	orgB := uuid.MustParse("550e8400-e29b-41d4-a716-446655440002")
	slider := newTestSlider(t, RedisSliderConfig{
		DefaultRPM:   60,
		OrgOverrides: map[uuid.UUID]int64{orgA: 2},
	})

	assertAllowedN(t, slider, orgA, 2)
	assertDenied(t, slider, orgA)
	assertAllowed(t, slider, orgB)
}

func newTestSlider(t *testing.T, cfg RedisSliderConfig) Limiter {
	t.Helper()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	slider, err := NewRedisSlider(client, cfg)
	if err != nil {
		t.Fatalf("NewRedisSlider: %v", err)
	}
	return slider
}

func checkN(t *testing.T, slider Limiter, orgID uuid.UUID, n int) Result {
	t.Helper()
	var result Result
	for i := 0; i < n; i++ {
		var err error
		result, err = slider.Check(context.Background(), orgID, uuid.Nil)
		if err != nil {
			t.Fatalf("Check: %v", err)
		}
	}
	return result
}

func assertLimitResult(t *testing.T, result Result, wantAllowed bool, wantRemain int, wantLimit int64) {
	t.Helper()
	if result.Allowed != wantAllowed {
		t.Errorf("Allowed = %v, want %v", result.Allowed, wantAllowed)
	}
	if result.Remaining != wantRemain {
		t.Errorf("Remaining = %d, want %d", result.Remaining, wantRemain)
	}
	if result.Limit != int(wantLimit) {
		t.Errorf("Limit = %d, want %d", result.Limit, wantLimit)
	}
	if result.ResetUnix <= 0 {
		t.Error("ResetUnix should be positive")
	}
}

func assertAllowedN(t *testing.T, slider Limiter, orgID uuid.UUID, n int) {
	t.Helper()
	for i := 0; i < n; i++ {
		assertAllowed(t, slider, orgID)
	}
}

func assertAllowed(t *testing.T, slider Limiter, orgID uuid.UUID) {
	t.Helper()
	res, err := slider.Check(context.Background(), orgID, uuid.Nil)
	if err != nil {
		t.Fatalf("Check: %v", err)
	}
	if !res.Allowed {
		t.Fatal("expected allowed")
	}
}

func assertDenied(t *testing.T, slider Limiter, orgID uuid.UUID) {
	t.Helper()
	res, err := slider.Check(context.Background(), orgID, uuid.Nil)
	if err != nil {
		t.Fatalf("Check: %v", err)
	}
	if res.Allowed {
		t.Fatal("expected denied")
	}
}

func TestNewRedisSlider_defaultRPMWhenZero(t *testing.T) {
	t.Parallel()
	slider := newTestSlider(t, RedisSliderConfig{DefaultRPM: 0})
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

	slider, sErr := NewRedisSlider(client, RedisSliderConfig{DefaultRPM: 60})
	if sErr != nil {
		t.Fatalf("NewRedisSlider: %v", sErr)
	}
	_, err := slider.Check(context.Background(), uuid.MustParse("550e8400-e29b-41d4-a716-446655440000"), uuid.Nil)
	if err == nil {
		t.Fatal("expected redis infrastructure error")
	}
}

func TestRedisSlider_orgOverrideZeroUsesDefault(t *testing.T) {
	t.Parallel()
	orgID := uuid.MustParse("550e8400-e29b-41d4-a716-446655440003")
	slider := newTestSlider(t, RedisSliderConfig{
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
