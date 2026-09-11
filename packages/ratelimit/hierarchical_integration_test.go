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

type integrationBurstRun struct {
	tc            tierBurstCase
	rpm           int64
	agentOverride int64
}

func runIntegrationExactBurst(t *testing.T, run integrationBurstRun) {
	t.Helper()
	lim := newIntegrationHierarchical(t, run.tc.cfg)
	if run.agentOverride > 0 {
		lim.ApplyOrgOverrides(run.tc.org, OrgOverrideSet{
			AgentRPM: map[uuid.UUID]int64{run.tc.agent: run.agentOverride},
		})
	}
	results := assertExactBurst(t, checkArgs{lim: lim, org: run.tc.org, agent: run.tc.agent}, run.rpm, integrationBurstWorkers)
	assertDeniedTier(t, results, run.tc.wantTier)
	allowed := countAllowed(results)
	t.Logf("tier=%s admitted=%d rejected=%d workers=%d rpm=%d",
		run.tc.wantTier, allowed, integrationBurstWorkers-allowed, integrationBurstWorkers, run.rpm)
}

func TestIntegration_Hierarchical_ZeroOverAdmission_200x100(t *testing.T) {
	const rpm = integrationBurstRPM
	ids := tierBurstIDs{
		orgOrg:    uuid.MustParse("550e8400-e29b-41d4-a716-446655441001"),
		orgAgent:  uuid.MustParse("550e8400-e29b-41d4-a716-446655441002"),
		orgGlobal: uuid.MustParse("550e8400-e29b-41d4-a716-446655441003"),
		agent:     uuid.MustParse("550e8400-e29b-41d4-a716-446655441101"),
	}
	for _, tc := range hierarchicalTierBurstCases(rpm, ids) {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			runIntegrationExactBurst(t, integrationBurstRun{tc: tc, rpm: rpm})
		})
	}
	t.Run("agent_via_ApplyOrgOverrides", func(t *testing.T) {
		runIntegrationExactBurst(t, integrationBurstRun{
			tc: tierBurstCase{
				cfg: HierarchicalConfig{
					DefaultRPM: 10_000,
					GlobalRPM:  10_000,
				},
				org:      uuid.MustParse("550e8400-e29b-41d4-a716-446655441004"),
				agent:    uuid.MustParse("550e8400-e29b-41d4-a716-446655441102"),
				wantTier: tierAgent,
			},
			rpm:           rpm,
			agentOverride: rpm,
		})
	})
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
	assertCrossOrgAfterExhaust(t, crossOrgExhaust{
		lim: lim, orgA: orgA, orgB: orgB, agent: agent, wantDenyTier: tierAgent,
	})
}
