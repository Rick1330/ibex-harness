//go:build integration

package ratelimit

import (
	"context"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

// Milestone 4.B.3 success signal: 200 concurrent / RPM 100, zero over/under admission.
const (
	integrationBurstWorkers = 200
	integrationBurstRPM     = 100
	// Dedicated DB so FLUSHDB does not collide with other packages on DB 0.
	integrationRedisURLDefault = "redis://127.0.0.1:6379/14"
)

func requireIntegrationRedis(t *testing.T) redis.UniversalClient {
	t.Helper()
	raw := strings.TrimSpace(os.Getenv("REDIS_URL"))
	if raw == "" {
		raw = integrationRedisURLDefault
	}
	opts, err := redis.ParseURL(raw)
	if err != nil {
		t.Skipf("REDIS_URL parse failed: %v", err)
	}
	// Keep skip-on-unreachable fast for coverage CI (no Redis service).
	opts.DialTimeout = 200 * time.Millisecond
	opts.MaxRetries = 0
	client := redis.NewClient(opts)
	ctx, cancel := context.WithTimeout(context.Background(), 500*time.Millisecond)
	defer cancel()
	if err := client.Ping(ctx).Err(); err != nil {
		_ = client.Close()
		t.Skipf("Redis unreachable (%s): %v", raw, err)
	}
	flushCtx, flushCancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer flushCancel()
	if err := client.FlushDB(flushCtx).Err(); err != nil {
		_ = client.Close()
		t.Fatalf("FlushDB: %v", err)
	}
	t.Cleanup(func() { _ = client.Close() })
	return client
}

func newIntegrationHierarchical(t *testing.T, cfg HierarchicalConfig) *HierarchicalLimiter {
	t.Helper()
	client := requireIntegrationRedis(t)
	limIface, err := NewHierarchicalLimiter(client, cfg)
	if err != nil {
		t.Fatalf("NewHierarchicalLimiter: %v", err)
	}
	lim, ok := AsHierarchical(limIface)
	if !ok {
		t.Fatal("expected *HierarchicalLimiter")
	}
	return lim
}

func assertExactBurstRPMN(t *testing.T, args checkArgs, rpm int64, workers int, wantTier string) (allowed, denied int) {
	t.Helper()
	results := burstCheckHierarchical(t, args, workers)
	allowed = countAllowed(results)
	denied = workers - allowed
	assertAdmitWithinRaceBound(t, allowed, rpm, maxAdmitOvershoot)
	assertSomeDenied(t, allowed, workers)
	if allowed != int(rpm) {
		t.Fatalf("allowed=%d want exactly RPM=%d (zero overshoot)", allowed, rpm)
	}
	if denied != workers-int(rpm) {
		t.Fatalf("denied=%d want exactly %d", denied, workers-int(rpm))
	}
	assertDeniedTier(t, results, wantTier)
	return allowed, denied
}

func TestIntegration_Hierarchical_ZeroOverAdmission_200x100(t *testing.T) {
	const rpm = integrationBurstRPM
	orgOrg := uuid.MustParse("550e8400-e29b-41d4-a716-446655441001")
	orgAgent := uuid.MustParse("550e8400-e29b-41d4-a716-446655441002")
	orgGlobal := uuid.MustParse("550e8400-e29b-41d4-a716-446655441003")
	orgDB := uuid.MustParse("550e8400-e29b-41d4-a716-446655441004")
	agent := uuid.MustParse("550e8400-e29b-41d4-a716-446655441101")
	agentDB := uuid.MustParse("550e8400-e29b-41d4-a716-446655441102")

	cases := []struct {
		name     string
		setup    func(t *testing.T) checkArgs
		wantTier string
	}{
		{
			name: "org",
			setup: func(t *testing.T) checkArgs {
				lim := newIntegrationHierarchical(t, HierarchicalConfig{
					DefaultRPM:   10_000,
					OrgOverrides: map[uuid.UUID]int64{orgOrg: rpm},
					GlobalRPM:    10_000,
				})
				return checkArgs{lim: lim, org: orgOrg, agent: uuid.Nil}
			},
			wantTier: tierOrg,
		},
		{
			name: "agent",
			setup: func(t *testing.T) checkArgs {
				lim := newIntegrationHierarchical(t, HierarchicalConfig{
					DefaultRPM:   rpm,
					OrgOverrides: map[uuid.UUID]int64{orgAgent: 10_000},
					GlobalRPM:    10_000,
				})
				return checkArgs{lim: lim, org: orgAgent, agent: agent}
			},
			wantTier: tierAgent,
		},
		{
			name: "global",
			setup: func(t *testing.T) checkArgs {
				lim := newIntegrationHierarchical(t, HierarchicalConfig{
					DefaultRPM: 10_000,
					GlobalRPM:  rpm,
				})
				return checkArgs{lim: lim, org: orgGlobal, agent: uuid.Nil}
			},
			wantTier: tierGlobal,
		},
		{
			name: "agent_via_ApplyOrgOverrides",
			setup: func(t *testing.T) checkArgs {
				lim := newIntegrationHierarchical(t, HierarchicalConfig{
					DefaultRPM: 10_000,
					GlobalRPM:  10_000,
				})
				lim.ApplyOrgOverrides(orgDB, OrgOverrideSet{
					AgentRPM: map[uuid.UUID]int64{agentDB: rpm},
				})
				return checkArgs{lim: lim, org: orgDB, agent: agentDB}
			},
			wantTier: tierAgent,
		},
	}

	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			args := tc.setup(t)
			allowed, denied := assertExactBurstRPMN(
				t, args, rpm, integrationBurstWorkers, tc.wantTier,
			)
			t.Logf("tier=%s admitted=%d rejected=%d workers=%d rpm=%d",
				tc.wantTier, allowed, denied, integrationBurstWorkers, rpm)
		})
	}
}

func TestIntegration_Hierarchical_sameAgentDifferentOrgsIndependent(t *testing.T) {
	orgA := uuid.MustParse("550e8400-e29b-41d4-a716-446655441010")
	orgB := uuid.MustParse("550e8400-e29b-41d4-a716-446655441011")
	agent := uuid.MustParse("550e8400-e29b-41d4-a716-446655441110")
	lim := newIntegrationHierarchical(t, HierarchicalConfig{
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
}
