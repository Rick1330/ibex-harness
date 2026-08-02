package ratelimit

import (
	"context"
	"sync"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

// Soft-limit race bound for RedisSlider (ADR-0015 / MF-007).
// Redis INCR via Lua is atomic with EXPIRE-on-create, so admit decisions never
// exceed DefaultRPM under concurrency (maxAdmitOvershoot = 0).
const maxAdmitOvershoot = 0

const (
	concurrentBurstWorkers = 80
	concurrentBurstRPM     = 20
)

type limitExpect struct {
	allowed bool
	remain  int
	limit   int64
}

func TestRedisSlider_underAtOverLimit(t *testing.T) {
	t.Parallel()

	testOrgID := uuid.MustParse("550e8400-e29b-41d4-a716-446655440000")
	tests := []struct {
		name     string
		requests int
		limit    int64
		want     limitExpect
	}{
		{name: "under limit", requests: 10, limit: 60, want: limitExpect{allowed: true, remain: 50, limit: 60}},
		{name: "at limit", requests: 60, limit: 60, want: limitExpect{allowed: true, remain: 0, limit: 60}},
		{name: "over limit", requests: 61, limit: 60, want: limitExpect{allowed: false, remain: 0, limit: 60}},
	}

	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			slider := newTestSlider(t, RedisSliderConfig{DefaultRPM: tc.limit})
			result := checkN(t, slider, testOrgID, tc.requests)
			assertLimitResult(t, result, tc.want)
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
	assertCheckAllowed(t, slider, orgA, false)
	assertCheckAllowed(t, slider, orgB, true)
}

// TestRedisSlider_ConcurrentBurst verifies concurrent Check calls for one org
// do not admit more than DefaultRPM + maxAdmitOvershoot (documented race bound).
func TestRedisSlider_ConcurrentBurst(t *testing.T) {
	t.Parallel()

	orgID := uuid.MustParse("550e8400-e29b-41d4-a716-446655440010")
	slider := newTestSlider(t, RedisSliderConfig{DefaultRPM: concurrentBurstRPM})

	results := burstCheck(t, slider, orgID, concurrentBurstWorkers)
	allowed := countAllowed(results)
	assertAdmitWithinRaceBound(t, allowed, concurrentBurstRPM, maxAdmitOvershoot)
	assertSomeDenied(t, allowed, concurrentBurstWorkers)
}

func newTestSlider(t testing.TB, cfg RedisSliderConfig) Limiter {
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

func burstCheck(t *testing.T, slider Limiter, orgID uuid.UUID, n int) []Result {
	t.Helper()
	results := make([]Result, n)
	errs := make([]error, n)
	var wg sync.WaitGroup
	wg.Add(n)
	for i := 0; i < n; i++ {
		i := i
		go func() {
			defer wg.Done()
			res, err := slider.Check(context.Background(), orgID, uuid.Nil)
			results[i] = res
			errs[i] = err
		}()
	}
	wg.Wait()
	assertNoCheckErrors(t, errs)
	return results
}

func assertNoCheckErrors(t *testing.T, errs []error) {
	t.Helper()
	for i, err := range errs {
		if err != nil {
			t.Fatalf("Check[%d]: %v", i, err)
		}
	}
}

func countAllowed(results []Result) int {
	n := 0
	for _, r := range results {
		if r.Allowed {
			n++
		}
	}
	return n
}

func assertAdmitWithinRaceBound(t *testing.T, allowed int, limit int64, overshoot int) {
	t.Helper()
	maxAllowed := int(limit) + overshoot
	if allowed > maxAllowed {
		t.Fatalf("allowed=%d exceeds RPM=%d + overshoot=%d", allowed, limit, overshoot)
	}
	if allowed < 1 {
		t.Fatal("expected at least one allowed request")
	}
}

func assertSomeDenied(t *testing.T, allowed, workers int) {
	t.Helper()
	if allowed >= workers {
		t.Fatalf("allowed=%d workers=%d: expected denials when workers exceed RPM", allowed, workers)
	}
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

func assertLimitResult(t *testing.T, result Result, want limitExpect) {
	t.Helper()
	if result.Allowed != want.allowed {
		t.Errorf("Allowed = %v, want %v", result.Allowed, want.allowed)
	}
	if result.Remaining != want.remain {
		t.Errorf("Remaining = %d, want %d", result.Remaining, want.remain)
	}
	if result.Limit != int(want.limit) {
		t.Errorf("Limit = %d, want %d", result.Limit, want.limit)
	}
	if result.ResetUnix <= 0 {
		t.Error("ResetUnix should be positive")
	}
}

func assertAllowedN(t *testing.T, slider Limiter, orgID uuid.UUID, n int) {
	t.Helper()
	for i := 0; i < n; i++ {
		assertCheckAllowed(t, slider, orgID, true)
	}
}

func assertCheckAllowed(t *testing.T, slider Limiter, orgID uuid.UUID, wantAllowed bool) {
	t.Helper()
	res, err := slider.Check(context.Background(), orgID, uuid.Nil)
	if err != nil {
		t.Fatalf("Check: %v", err)
	}
	if res.Allowed != wantAllowed {
		t.Fatalf("allowed = %v, want %v", res.Allowed, wantAllowed)
	}
}

func TestUnit_NewRedisSlider_RejectsNilClient(t *testing.T) {
	t.Parallel()
	_, err := NewRedisSlider(nil, RedisSliderConfig{DefaultRPM: 60})
	if err == nil {
		t.Fatal("expected error for nil client")
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
