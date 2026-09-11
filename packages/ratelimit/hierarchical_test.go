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
	assertRedisInt(t, mr, orgRPMKey(org, window.unixMinute), 1)
	assertRedisInt(t, mr, globalRPMKey(window.unixMinute), 1)
}

func TestHierarchical_tierTripsIndependent(t *testing.T) {
	t.Parallel()
	orgAgent := uuid.MustParse("550e8400-e29b-41d4-a716-446655440102")
	agentA := uuid.MustParse("550e8400-e29b-41d4-a716-446655440202")
	orgOrg := uuid.MustParse("550e8400-e29b-41d4-a716-446655440103")
	agentO := uuid.MustParse("550e8400-e29b-41d4-a716-446655440203")
	orgGlobal := uuid.MustParse("550e8400-e29b-41d4-a716-446655440104")
	agentG := uuid.MustParse("550e8400-e29b-41d4-a716-446655440204")
	cases := []struct {
		name   string
		cfg    HierarchicalConfig
		expect tripExpect
	}{
		{
			name: "agent",
			cfg: HierarchicalConfig{
				DefaultRPM: 2, OrgOverrides: map[uuid.UUID]int64{orgAgent: 100}, GlobalRPM: 1000,
			},
			expect: tripExpect{org: orgAgent, agent: agentA, wantTier: tierAgent, agentN: 3, orgN: 2, globalN: 2},
		},
		{
			name: "org",
			cfg: HierarchicalConfig{
				DefaultRPM: 100, OrgOverrides: map[uuid.UUID]int64{orgOrg: 2}, GlobalRPM: 1000,
			},
			expect: tripExpect{org: orgOrg, agent: agentO, wantTier: tierOrg, agentN: 2, orgN: 3, globalN: 2},
		},
		{
			name:   "global",
			cfg:    HierarchicalConfig{DefaultRPM: 100, GlobalRPM: 2},
			expect: tripExpect{org: orgGlobal, agent: agentG, wantTier: tierGlobal, agentN: 2, orgN: 2, globalN: 3},
		},
	}
	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			mr, lim := newTestHierarchicalMR(t, tc.cfg)
			runTripAndAssertCounters(t, mr, lim, tc.expect)
		})
	}
}

func TestHierarchical_sameAgentDifferentOrgsIndependent(t *testing.T) {
	t.Parallel()
	orgA := uuid.MustParse("550e8400-e29b-41d4-a716-446655440130")
	orgB := uuid.MustParse("550e8400-e29b-41d4-a716-446655440131")
	agent := uuid.MustParse("550e8400-e29b-41d4-a716-446655440230")
	mr, lim := newTestHierarchicalMR(t, HierarchicalConfig{
		DefaultRPM: 100,
		OrgOverrides: map[uuid.UUID]int64{
			orgA: 2,
			orgB: 100,
		},
		GlobalRPM: 10_000,
	})
	assertCheckWant(t, checkArgs{lim: lim, org: orgA, agent: agent}, true)
	assertCheckWant(t, checkArgs{lim: lim, org: orgA, agent: agent}, true)
	res := assertCheckWant(t, checkArgs{lim: lim, org: orgA, agent: agent}, false)
	if res.DeniedTier != tierOrg {
		t.Fatalf("DeniedTier=%q want org", res.DeniedTier)
	}
	assertCheckWant(t, checkArgs{lim: lim, org: orgB, agent: agent}, true)
	window := currentMinuteWindow(time.Now().UTC())
	assertRedisInt(t, mr, agentRPMKey(orgA, agent, window.unixMinute), 2)
	assertRedisInt(t, mr, orgRPMKey(orgA, window.unixMinute), 3)
	assertRedisInt(t, mr, agentRPMKey(orgB, agent, window.unixMinute), 1)
	assertRedisInt(t, mr, orgRPMKey(orgB, window.unixMinute), 1)
}

func TestHierarchical_ConcurrentBurst(t *testing.T) {
	t.Parallel()
	const rpm = 20
	orgOrg := uuid.MustParse("550e8400-e29b-41d4-a716-446655440110")
	orgAgent := uuid.MustParse("550e8400-e29b-41d4-a716-446655440111")
	agent := uuid.MustParse("550e8400-e29b-41d4-a716-446655440211")
	orgGlobal := uuid.MustParse("550e8400-e29b-41d4-a716-446655440112")
	cases := []struct {
		name     string
		cfg      HierarchicalConfig
		org      uuid.UUID
		agent    uuid.UUID
		wantTier string
	}{
		{
			name: "org",
			cfg: HierarchicalConfig{
				DefaultRPM: 10_000, OrgOverrides: map[uuid.UUID]int64{orgOrg: rpm}, GlobalRPM: 10_000,
			},
			org: orgOrg, wantTier: tierOrg,
		},
		{
			name: "agent",
			cfg: HierarchicalConfig{
				DefaultRPM: rpm, OrgOverrides: map[uuid.UUID]int64{orgAgent: 10_000}, GlobalRPM: 10_000,
			},
			org: orgAgent, agent: agent, wantTier: tierAgent,
		},
		{
			name: "global",
			cfg:  HierarchicalConfig{DefaultRPM: 10_000, GlobalRPM: rpm},
			org:  orgGlobal, wantTier: tierGlobal,
		},
	}
	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			runBurstExactRPM(t, burstCase{
				cfg: tc.cfg, args: checkArgs{org: tc.org, agent: tc.agent},
				rpm: rpm, wantTier: tc.wantTier,
			})
		})
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

func TestUnit_resultFromHierarchical_shortReply(t *testing.T) {
	t.Parallel()
	window := currentMinuteWindow(time.Now().UTC())
	_, err := resultFromHierarchical([]any{int64(1)}, 60, window)
	if err == nil {
		t.Fatal("expected short-reply error")
	}
}

func TestUnit_resultFromHierarchical_parseErrors(t *testing.T) {
	t.Parallel()
	window := currentMinuteWindow(time.Now().UTC())
	cases := [][]any{
		{"x", "", int64(1), int64(60)},
		{int64(1), "", "bad", int64(60)},
		{int64(1), "", int64(1), "bad"},
	}
	for _, reply := range cases {
		_, err := resultFromHierarchical(reply, 60, window)
		if err == nil {
			t.Fatalf("expected parse error for %#v", reply)
		}
	}
}

func TestUnit_resultFromHierarchical_denyFallback(t *testing.T) {
	t.Parallel()
	window := currentMinuteWindow(time.Now().UTC())
	res, err := resultFromHierarchical([]any{int64(0), "", int64(3), int64(0)}, 60, window)
	if err != nil {
		t.Fatal(err)
	}
	if res.Allowed {
		t.Fatal("expected deny")
	}
	if res.DeniedTier != tierOrg {
		t.Fatalf("DeniedTier=%q", res.DeniedTier)
	}
	if res.Limit != 60 {
		t.Fatalf("Limit=%d", res.Limit)
	}
}

func TestUnit_resultFromHierarchical_allowIntBytes(t *testing.T) {
	t.Parallel()
	window := currentMinuteWindow(time.Now().UTC())
	res, err := resultFromHierarchical([]any{int(1), []byte(""), int64(1), int64(10)}, 10, window)
	if err != nil {
		t.Fatal(err)
	}
	if !res.Allowed || res.Limit != 10 {
		t.Fatalf("allow int/bytes: %+v", res)
	}
}

func TestUnit_asString(t *testing.T) {
	t.Parallel()
	if asString("a") != "a" {
		t.Fatal("string")
	}
	if asString([]byte("b")) != "b" {
		t.Fatal("bytes")
	}
	if asString(3) != "3" {
		t.Fatal("fallback")
	}
}

func TestUnit_asInt64_ok(t *testing.T) {
	t.Parallel()
	assertAsInt64(t, int64(7), 7)
	assertAsInt64(t, int(8), 8)
	assertAsInt64(t, "9", 9)
	assertAsInt64(t, []byte("10"), 10)
}

func TestUnit_asInt64_badType(t *testing.T) {
	t.Parallel()
	_, err := asInt64(struct{}{})
	if err == nil {
		t.Fatal("expected type error")
	}
}

type checkArgs struct {
	lim   Limiter
	org   uuid.UUID
	agent uuid.UUID
}

type tripExpect struct {
	org, agent            uuid.UUID
	wantTier              string
	agentN, orgN, globalN int64
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

func assertCheckWant(t *testing.T, args checkArgs, want bool) Result {
	t.Helper()
	res, err := args.lim.Check(context.Background(), args.org, args.agent)
	if err != nil {
		t.Fatalf("Check: %v", err)
	}
	if res.Allowed != want {
		t.Fatalf("allowed=%v want %v result=%+v", res.Allowed, want, res)
	}
	return res
}

func runTripAndAssertCounters(t *testing.T, mr *miniredis.Miniredis, lim Limiter, expect tripExpect) {
	t.Helper()
	args := checkArgs{lim: lim, org: expect.org, agent: expect.agent}
	assertCheckWant(t, args, true)
	assertCheckWant(t, args, true)
	res := assertCheckWant(t, args, false)
	if res.DeniedTier != expect.wantTier {
		t.Fatalf("DeniedTier=%q want %q", res.DeniedTier, expect.wantTier)
	}
	window := currentMinuteWindow(time.Now().UTC())
	assertRedisInt(t, mr, agentRPMKey(expect.org, expect.agent, window.unixMinute), expect.agentN)
	assertRedisInt(t, mr, orgRPMKey(expect.org, window.unixMinute), expect.orgN)
	assertRedisInt(t, mr, globalRPMKey(window.unixMinute), expect.globalN)
}

func burstCheckHierarchical(t *testing.T, args checkArgs, n int) []Result {
	t.Helper()
	results := make([]Result, n)
	errs := make([]error, n)
	var wg sync.WaitGroup
	wg.Add(n)
	for i := 0; i < n; i++ {
		i := i
		go func() {
			defer wg.Done()
			res, err := args.lim.Check(context.Background(), args.org, args.agent)
			results[i] = res
			errs[i] = err
		}()
	}
	wg.Wait()
	assertNoCheckErrors(t, errs)
	return results
}

type burstCase struct {
	cfg      HierarchicalConfig
	args     checkArgs
	rpm      int64
	wantTier string
}

func runBurstExactRPM(t *testing.T, bc burstCase) {
	t.Helper()
	bc.args.lim = newTestHierarchical(t, bc.cfg)
	results := assertExactBurstRPM(t, bc.args, bc.rpm)
	assertDeniedTier(t, results, bc.wantTier)
}

func assertExactBurstRPM(t *testing.T, args checkArgs, rpm int64) []Result {
	t.Helper()
	return assertExactBurst(t, args, rpm, concurrentBurstWorkers)
}

func assertExactBurst(t *testing.T, args checkArgs, rpm int64, workers int) []Result {
	t.Helper()
	results := burstCheckHierarchical(t, args, workers)
	allowed := countAllowed(results)
	assertAdmitWithinRaceBound(t, allowed, rpm, maxAdmitOvershoot)
	assertSomeDenied(t, allowed, workers)
	if allowed != int(rpm) {
		t.Fatalf("allowed=%d want exactly RPM=%d (zero overshoot)", allowed, rpm)
	}
	return results
}

func assertDeniedTier(t *testing.T, results []Result, wantTier string) {
	t.Helper()
	for _, r := range results {
		if r.Allowed {
			continue
		}
		if r.DeniedTier != wantTier {
			t.Fatalf("denied tier=%q want %q", r.DeniedTier, wantTier)
		}
	}
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

func assertAsInt64(t *testing.T, in any, want int64) {
	t.Helper()
	n, err := asInt64(in)
	if err != nil {
		t.Fatalf("%T: %v", in, err)
	}
	if n != want {
		t.Fatalf("%T=%d want %d", in, n, want)
	}
}

// BenchmarkHierarchical_ReplaceAllOverrides justifies building maps off-lock:
// Check holds dbMu.RLock on every request; poll must not rebuild under Lock.
func BenchmarkHierarchical_ReplaceAllOverrides(b *testing.B) {
	limIface := newTestHierarchical(b, HierarchicalConfig{DefaultRPM: 60, GlobalRPM: 100_000})
	lim, ok := AsHierarchical(limIface)
	if !ok {
		b.Fatal("expected HierarchicalLimiter")
	}
	all := make(map[uuid.UUID]OrgOverrideSet, 64)
	for i := 0; i < 64; i++ {
		org := uuid.New()
		rpm := int64(10 + i)
		agent := uuid.New()
		all[org] = OrgOverrideSet{OrgRPM: &rpm, AgentRPM: map[uuid.UUID]int64{agent: rpm}}
	}
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		lim.ReplaceAllOverrides(all)
	}
}
