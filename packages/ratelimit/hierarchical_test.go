package ratelimit

import (
	"context"
	"strconv"
	"sync"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

func TestUnit_NewHierarchicalLimiter_RejectsNilClient(t *testing.T) {
	t.Parallel()
	_, err := NewHierarchicalLimiter(nil, HierarchicalConfig{DefaultRPM: 60})
	if err == nil {
		t.Fatal("expected error for nil client")
	}
}

func TestHierarchical_defaultRPMAndGlobalWhenZero(t *testing.T) {
	t.Parallel()
	lim := newTestHierarchical(t, HierarchicalConfig{})
	org := uuid.MustParse("550e8400-e29b-41d4-a716-446655440100")
	res, err := lim.Check(context.Background(), org, uuid.Nil)
	if err != nil {
		t.Fatal(err)
	}
	if !res.Allowed || res.Limit != 60 {
		t.Fatalf("result: %+v", res)
	}
}

func TestHierarchical_nilAgentSkipsAgentTier(t *testing.T) {
	t.Parallel()
	mr, lim := newTestHierarchicalMR(t, HierarchicalConfig{
		DefaultRPM: 10,
		GlobalRPM:  1000,
	})
	org := uuid.MustParse("550e8400-e29b-41d4-a716-446655440101")
	res, err := lim.Check(context.Background(), org, uuid.Nil)
	if err != nil {
		t.Fatal(err)
	}
	if !res.Allowed || res.DeniedTier != "" {
		t.Fatalf("result: %+v", res)
	}
	window := currentMinuteWindow(time.Now().UTC())
	agentPrefix := "ratelimit:" + org.String() + ":agent:"
	for _, key := range mr.Keys() {
		if len(key) >= len(agentPrefix) && key[:len(agentPrefix)] == agentPrefix {
			t.Fatalf("unexpected agent key written: %s", key)
		}
	}
	orgKey := orgRPMKey(org, window.unixMinute)
	globalKey := globalRPMKey(window.unixMinute)
	assertRedisInt(t, mr, orgKey, 1)
	assertRedisInt(t, mr, globalKey, 1)
}

func TestHierarchical_agentTripIndependent(t *testing.T) {
	t.Parallel()
	org := uuid.MustParse("550e8400-e29b-41d4-a716-446655440102")
	agent := uuid.MustParse("550e8400-e29b-41d4-a716-446655440202")
	mr, lim := newTestHierarchicalMR(t, HierarchicalConfig{
		DefaultRPM:   2,
		OrgOverrides: map[uuid.UUID]int64{org: 100},
		GlobalRPM:    1000,
	})
	assertHierarchicalAllowed(t, lim, org, agent, true)
	assertHierarchicalAllowed(t, lim, org, agent, true)
	res := assertHierarchicalAllowed(t, lim, org, agent, false)
	if res.DeniedTier != tierAgent {
		t.Fatalf("DeniedTier=%q want agent", res.DeniedTier)
	}
	window := currentMinuteWindow(time.Now().UTC())
	assertRedisInt(t, mr, agentRPMKey(org, agent, window.unixMinute), 3)
	assertRedisInt(t, mr, orgRPMKey(org, window.unixMinute), 2)
	assertRedisInt(t, mr, globalRPMKey(window.unixMinute), 2)
}

func TestHierarchical_orgTripIndependent(t *testing.T) {
	t.Parallel()
	org := uuid.MustParse("550e8400-e29b-41d4-a716-446655440103")
	agent := uuid.MustParse("550e8400-e29b-41d4-a716-446655440203")
	mr, lim := newTestHierarchicalMR(t, HierarchicalConfig{
		DefaultRPM:   100,
		OrgOverrides: map[uuid.UUID]int64{org: 2},
		GlobalRPM:    1000,
	})
	assertHierarchicalAllowed(t, lim, org, agent, true)
	assertHierarchicalAllowed(t, lim, org, agent, true)
	res := assertHierarchicalAllowed(t, lim, org, agent, false)
	if res.DeniedTier != tierOrg {
		t.Fatalf("DeniedTier=%q want org", res.DeniedTier)
	}
	window := currentMinuteWindow(time.Now().UTC())
	assertRedisInt(t, mr, agentRPMKey(org, agent, window.unixMinute), 2) // rolled back on org deny
	assertRedisInt(t, mr, orgRPMKey(org, window.unixMinute), 3)
	assertRedisInt(t, mr, globalRPMKey(window.unixMinute), 2)
}

func TestHierarchical_globalTripIndependent(t *testing.T) {
	t.Parallel()
	org := uuid.MustParse("550e8400-e29b-41d4-a716-446655440104")
	agent := uuid.MustParse("550e8400-e29b-41d4-a716-446655440204")
	mr, lim := newTestHierarchicalMR(t, HierarchicalConfig{
		DefaultRPM: 100,
		GlobalRPM:  2,
	})
	assertHierarchicalAllowed(t, lim, org, agent, true)
	assertHierarchicalAllowed(t, lim, org, agent, true)
	res := assertHierarchicalAllowed(t, lim, org, agent, false)
	if res.DeniedTier != tierGlobal {
		t.Fatalf("DeniedTier=%q want global", res.DeniedTier)
	}
	window := currentMinuteWindow(time.Now().UTC())
	assertRedisInt(t, mr, agentRPMKey(org, agent, window.unixMinute), 2)
	assertRedisInt(t, mr, orgRPMKey(org, window.unixMinute), 2)
	assertRedisInt(t, mr, globalRPMKey(window.unixMinute), 3)
}

func TestHierarchical_ConcurrentBurst_orgTier(t *testing.T) {
	t.Parallel()
	org := uuid.MustParse("550e8400-e29b-41d4-a716-446655440110")
	const rpm = 20
	lim := newTestHierarchical(t, HierarchicalConfig{
		DefaultRPM:   10_000,
		OrgOverrides: map[uuid.UUID]int64{org: rpm},
		GlobalRPM:    10_000,
	})
	results := burstCheckHierarchical(t, lim, org, uuid.Nil, concurrentBurstWorkers)
	allowed := countAllowed(results)
	assertAdmitWithinRaceBound(t, allowed, rpm, maxAdmitOvershoot)
	assertSomeDenied(t, allowed, concurrentBurstWorkers)
	if allowed != int(rpm) {
		t.Fatalf("allowed=%d want exactly RPM=%d (zero overshoot)", allowed, rpm)
	}
}

func TestHierarchical_ConcurrentBurst_agentTier(t *testing.T) {
	t.Parallel()
	org := uuid.MustParse("550e8400-e29b-41d4-a716-446655440111")
	agent := uuid.MustParse("550e8400-e29b-41d4-a716-446655440211")
	const rpm = 20
	lim := newTestHierarchical(t, HierarchicalConfig{
		DefaultRPM:   rpm,
		OrgOverrides: map[uuid.UUID]int64{org: 10_000},
		GlobalRPM:    10_000,
	})
	results := burstCheckHierarchical(t, lim, org, agent, concurrentBurstWorkers)
	allowed := countAllowed(results)
	assertAdmitWithinRaceBound(t, allowed, rpm, maxAdmitOvershoot)
	assertSomeDenied(t, allowed, concurrentBurstWorkers)
	if allowed != int(rpm) {
		t.Fatalf("allowed=%d want exactly RPM=%d (zero overshoot)", allowed, rpm)
	}
	for _, r := range results {
		if !r.Allowed && r.DeniedTier != tierAgent {
			t.Fatalf("denied tier=%q want agent", r.DeniedTier)
		}
	}
}

func TestHierarchical_Check_redisError(t *testing.T) {
	t.Parallel()
	client := redis.NewClient(&redis.Options{
		Addr:         "127.0.0.1:1",
		DialTimeout:  50 * time.Millisecond,
		ReadTimeout:  50 * time.Millisecond,
		WriteTimeout: 50 * time.Millisecond,
		MaxRetries:   0,
	})
	t.Cleanup(func() { _ = client.Close() })
	lim, err := NewHierarchicalLimiter(client, HierarchicalConfig{DefaultRPM: 60, GlobalRPM: 1000})
	if err != nil {
		t.Fatal(err)
	}
	_, err = lim.Check(context.Background(), uuid.MustParse("550e8400-e29b-41d4-a716-446655440120"), uuid.Nil)
	if err == nil {
		t.Fatal("expected redis infrastructure error")
	}
}

func newTestHierarchical(t testing.TB, cfg HierarchicalConfig) Limiter {
	t.Helper()
	_, lim := newTestHierarchicalMR(t, cfg)
	return lim
}

func newTestHierarchicalMR(t testing.TB, cfg HierarchicalConfig) (*miniredis.Miniredis, Limiter) {
	t.Helper()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	lim, err := NewHierarchicalLimiter(client, cfg)
	if err != nil {
		t.Fatalf("NewHierarchicalLimiter: %v", err)
	}
	return mr, lim
}

func assertHierarchicalAllowed(t *testing.T, lim Limiter, org, agent uuid.UUID, want bool) Result {
	t.Helper()
	res, err := lim.Check(context.Background(), org, agent)
	if err != nil {
		t.Fatalf("Check: %v", err)
	}
	if res.Allowed != want {
		t.Fatalf("allowed=%v want %v result=%+v", res.Allowed, want, res)
	}
	return res
}

func burstCheckHierarchical(t *testing.T, lim Limiter, org, agent uuid.UUID, n int) []Result {
	t.Helper()
	results := make([]Result, n)
	errs := make([]error, n)
	var wg sync.WaitGroup
	wg.Add(n)
	for i := 0; i < n; i++ {
		i := i
		go func() {
			defer wg.Done()
			res, err := lim.Check(context.Background(), org, agent)
			results[i] = res
			errs[i] = err
		}()
	}
	wg.Wait()
	assertNoCheckErrors(t, errs)
	return results
}

func assertRedisInt(t *testing.T, mr *miniredis.Miniredis, key string, want int64) {
	t.Helper()
	got, err := mr.Get(key)
	if err != nil {
		t.Fatalf("GET %s: %v", key, err)
	}
	n, err := strconv.ParseInt(got, 10, 64)
	if err != nil {
		t.Fatalf("parse %s=%q: %v", key, got, err)
	}
	if n != want {
		t.Fatalf("%s=%d want %d", key, n, want)
	}
}

func TestUnit_resultFromHierarchical_edges(t *testing.T) {
	t.Parallel()
	window := currentMinuteWindow(time.Now().UTC())

	_, err := resultFromHierarchical([]any{int64(1)}, 60, window)
	if err == nil {
		t.Fatal("expected short-reply error")
	}

	_, err = resultFromHierarchical([]any{"x", "", int64(1), int64(60)}, 60, window)
	if err == nil {
		t.Fatal("expected allowed parse error")
	}

	_, err = resultFromHierarchical([]any{int64(1), "", "bad", int64(60)}, 60, window)
	if err == nil {
		t.Fatal("expected org_count parse error")
	}

	_, err = resultFromHierarchical([]any{int64(1), "", int64(1), "bad"}, 60, window)
	if err == nil {
		t.Fatal("expected org_limit parse error")
	}

	res, err := resultFromHierarchical([]any{int64(0), "", int64(3), int64(0)}, 60, window)
	if err != nil {
		t.Fatal(err)
	}
	if res.Allowed || res.DeniedTier != tierOrg || res.Limit != 60 {
		t.Fatalf("deny fallback: %+v", res)
	}

	res, err = resultFromHierarchical([]any{int(1), []byte(""), int64(1), int64(10)}, 10, window)
	if err != nil {
		t.Fatal(err)
	}
	if !res.Allowed || res.Limit != 10 {
		t.Fatalf("allow int/bytes: %+v", res)
	}
}

func TestUnit_asString_asInt64(t *testing.T) {
	t.Parallel()
	if asString("a") != "a" || asString([]byte("b")) != "b" || asString(3) != "3" {
		t.Fatal("asString cases")
	}
	n, err := asInt64(int64(7))
	if err != nil || n != 7 {
		t.Fatalf("int64: %d %v", n, err)
	}
	n, err = asInt64(int(8))
	if err != nil || n != 8 {
		t.Fatalf("int: %d %v", n, err)
	}
	n, err = asInt64("9")
	if err != nil || n != 9 {
		t.Fatalf("string: %d %v", n, err)
	}
	n, err = asInt64([]byte("10"))
	if err != nil || n != 10 {
		t.Fatalf("bytes: %d %v", n, err)
	}
	_, err = asInt64(struct{}{})
	if err == nil {
		t.Fatal("expected type error")
	}
}

func TestHierarchical_ConcurrentBurst_globalTier(t *testing.T) {
	t.Parallel()
	org := uuid.MustParse("550e8400-e29b-41d4-a716-446655440112")
	const rpm = 20
	lim := newTestHierarchical(t, HierarchicalConfig{
		DefaultRPM: 10_000,
		GlobalRPM:  rpm,
	})
	results := burstCheckHierarchical(t, lim, org, uuid.Nil, concurrentBurstWorkers)
	allowed := countAllowed(results)
	assertAdmitWithinRaceBound(t, allowed, rpm, maxAdmitOvershoot)
	assertSomeDenied(t, allowed, concurrentBurstWorkers)
	if allowed != int(rpm) {
		t.Fatalf("allowed=%d want exactly RPM=%d (zero overshoot)", allowed, rpm)
	}
	for _, r := range results {
		if !r.Allowed && r.DeniedTier != tierGlobal {
			t.Fatalf("denied tier=%q want global", r.DeniedTier)
		}
	}
}
