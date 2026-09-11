//go:build integration

package ratelimit

import (
	"context"
	"fmt"
	"net"
	"os"
	"strconv"
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
	// Dedicated DB so FLUSHDB cannot wipe shared DB 0 used by other packages.
	integrationRedisDB         = 14
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
		t.Fatalf("REDIS_URL parse failed: %v", err)
	}
	if err := validateIntegrationRedisOpts(opts); err != nil {
		t.Fatalf("REDIS_URL rejected: %v", err)
	}
	// Keep skip-on-unreachable fast for coverage CI (no Redis service).
	opts.DialTimeout = 200 * time.Millisecond
	opts.MaxRetries = 0
	client := redis.NewClient(opts)
	endpoint := redactRedisEndpoint(opts)
	ctx, cancel := context.WithTimeout(context.Background(), 500*time.Millisecond)
	defer cancel()
	if err := client.Ping(ctx).Err(); err != nil {
		_ = client.Close()
		t.Skipf("Redis unreachable (%s): %v", endpoint, err)
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

func validateIntegrationRedisOpts(opts *redis.Options) error {
	if opts == nil {
		return fmt.Errorf("nil redis options")
	}
	if opts.DB != integrationRedisDB {
		return fmt.Errorf("must use DB %d for isolated FlushDB (got %d)", integrationRedisDB, opts.DB)
	}
	hasCreds := opts.Username != "" || opts.Password != ""
	if !hasCreds {
		return nil
	}
	if opts.TLSConfig != nil {
		return nil
	}
	if isLoopbackRedisAddr(opts.Addr) {
		return nil
	}
	return fmt.Errorf("credentialed redis:// to non-loopback requires rediss:// (TLS)")
}

func isLoopbackRedisAddr(addr string) bool {
	host, _, err := net.SplitHostPort(addr)
	if err != nil {
		host = addr
	}
	host = strings.Trim(host, "[]")
	if strings.EqualFold(host, "localhost") {
		return true
	}
	ip := net.ParseIP(host)
	return ip != nil && ip.IsLoopback()
}

func redactRedisEndpoint(opts *redis.Options) string {
	return opts.Addr + "/" + strconv.Itoa(opts.DB)
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

func TestIntegration_Hierarchical_ZeroOverAdmission_200x100(t *testing.T) {
	const rpm = integrationBurstRPM
	orgOrg := uuid.MustParse("550e8400-e29b-41d4-a716-446655441001")
	orgAgent := uuid.MustParse("550e8400-e29b-41d4-a716-446655441002")
	orgGlobal := uuid.MustParse("550e8400-e29b-41d4-a716-446655441003")
	orgDB := uuid.MustParse("550e8400-e29b-41d4-a716-446655441004")
	agent := uuid.MustParse("550e8400-e29b-41d4-a716-446655441101")
	agentDB := uuid.MustParse("550e8400-e29b-41d4-a716-446655441102")

	cases := []struct {
		name          string
		cfg           HierarchicalConfig
		org, agent    uuid.UUID
		agentOverride int64 // when >0, ApplyOrgOverrides seeds binding agent RPM
		wantTier      string
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
		{
			name: "agent_via_ApplyOrgOverrides",
			cfg: HierarchicalConfig{
				DefaultRPM: 10_000, GlobalRPM: 10_000,
			},
			org: orgDB, agent: agentDB, agentOverride: rpm, wantTier: tierAgent,
		},
	}

	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			lim := newIntegrationHierarchical(t, tc.cfg)
			if tc.agentOverride > 0 {
				lim.ApplyOrgOverrides(tc.org, OrgOverrideSet{
					AgentRPM: map[uuid.UUID]int64{tc.agent: tc.agentOverride},
				})
			}
			results := assertExactBurst(t, checkArgs{lim: lim, org: tc.org, agent: tc.agent}, rpm, integrationBurstWorkers)
			assertDeniedTier(t, results, tc.wantTier)
			allowed := countAllowed(results)
			t.Logf("tier=%s admitted=%d rejected=%d workers=%d rpm=%d",
				tc.wantTier, allowed, integrationBurstWorkers-allowed, integrationBurstWorkers, rpm)
		})
	}
}

func TestIntegration_Hierarchical_sameAgentDifferentOrgsIndependent(t *testing.T) {
	orgA := uuid.MustParse("550e8400-e29b-41d4-a716-446655441010")
	orgB := uuid.MustParse("550e8400-e29b-41d4-a716-446655441011")
	agent := uuid.MustParse("550e8400-e29b-41d4-a716-446655441110")
	// Org limits stay high so Org A denials bind on the per-agent tier (cross-org key isolation).
	lim := newIntegrationHierarchical(t, HierarchicalConfig{
		DefaultRPM: 100,
		OrgOverrides: map[uuid.UUID]int64{
			orgA: 10_000,
			orgB: 10_000,
		},
		GlobalRPM: 10_000,
	})
	lim.ApplyOrgOverrides(orgA, OrgOverrideSet{
		AgentRPM: map[uuid.UUID]int64{agent: 2},
	})
	assertCheckWant(t, checkArgs{lim: lim, org: orgA, agent: agent}, true)
	assertCheckWant(t, checkArgs{lim: lim, org: orgA, agent: agent}, true)
	res := assertCheckWant(t, checkArgs{lim: lim, org: orgA, agent: agent}, false)
	if res.DeniedTier != tierAgent {
		t.Fatalf("DeniedTier=%q want agent", res.DeniedTier)
	}
	assertCheckWant(t, checkArgs{lim: lim, org: orgB, agent: agent}, true)
}
