package bootstrap

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/billing"
	"github.com/Rick1330/ibex-harness/packages/logger"
	ibexmetrics "github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/alicebob/miniredis/v2"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

type fakeBudgetLoader struct {
	snap billing.BudgetSnapshot
	err  error
}

func (f fakeBudgetLoader) LoadOrg(context.Context, uuid.UUID) (billing.BudgetSnapshot, error) {
	if f.err != nil {
		return billing.BudgetSnapshot{}, f.err
	}
	return f.snap, nil
}

func TestUnit_BillingMetrics_NilAndAdapter(t *testing.T) {
	t.Parallel()

	noop := billingMetrics(nil)
	if _, ok := noop.(billing.NoopMetrics); !ok {
		t.Fatalf("nil reg: got %T want billing.NoopMetrics", noop)
	}

	reg := ibexmetrics.NewProxy("billing-metrics-adapter-test")
	got := billingMetrics(reg)
	adapter, ok := got.(budgetMetricsAdapter)
	if !ok {
		t.Fatalf("non-nil reg: got %T want budgetMetricsAdapter", got)
	}
	if adapter.reg != reg {
		t.Fatal("adapter registry mismatch")
	}
	adapter.IncCacheHit("lru")
	adapter.IncCacheMiss("lru")
	adapter.IncDeny()
	adapter.IncInvalidate()
	adapter.SetLRUSize(1)
}

func TestUnit_NewBudgetCache_NilPostgres(t *testing.T) {
	t.Parallel()
	cache, err := newBudgetCache(nil, nil)
	if err != nil {
		t.Fatalf("err=%v", err)
	}
	if cache != nil {
		t.Fatal("expected nil cache without postgres")
	}
}

func TestUnit_StartBudgetSubscriber_SkippedWithoutDeps(t *testing.T) {
	t.Parallel()

	cache := mustBudgetCache(t)
	unusedRedis := redis.NewClient(&redis.Options{Addr: "127.0.0.1:0"})
	t.Cleanup(func() { _ = unusedRedis.Close() })

	cases := []struct {
		name  string
		redis redis.UniversalClient
		cache *billing.Cache
	}{
		{name: "nil redis and cache"},
		{name: "nil redis only", cache: cache},
		{name: "nil cache only", redis: unusedRedis},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			sub, cancel, err := startBudgetSubscriber(tc.redis, tc.cache, nil, nil)
			if err != nil {
				t.Fatalf("err=%v", err)
			}
			if sub != nil {
				t.Fatal("expected nil subscriber")
			}
			if cancel != nil {
				t.Fatal("expected nil cancel")
			}
		})
	}
}

func TestUnit_StartBudgetSubscriber_StartsAndStops(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })

	cache := mustBudgetCache(t)
	sub, cancel, err := startBudgetSubscriber(client, cache, logger.Discard("bootstrap-billing"), nil)
	if err != nil {
		t.Fatal(err)
	}
	if sub == nil || cancel == nil {
		t.Fatal("expected subscriber")
	}
	cancel()
	sub.Stop()
	select {
	case <-sub.Done():
	case <-time.After(3 * time.Second):
		t.Fatal("subscriber did not stop")
	}
}

func TestUnit_OptionalUsageFactWriter(t *testing.T) {
	t.Parallel()

	if optionalUsageFactWriter("", nil, nil, nil) != nil {
		t.Fatal("empty DSN: expected nil")
	}
	if optionalUsageFactWriter("not-a-clickhouse-dsn", logger.Discard("billing"), nil, nil) != nil {
		t.Fatal("bad DSN: expected nil")
	}
}

func TestUnit_OptionalUsageFactWriter_SuccessWiresOnDropMetrics(t *testing.T) {
	t.Parallel()

	ins := &stubUsageFactInserter{}
	factory := func(cfg billing.UsageFactConfig) (*billing.UsageFactWriter, error) {
		return billing.NewUsageFactWriterWithInserter(ins, billing.UsageFactConfig{
			DSN:           cfg.DSN,
			MaxBatchSize:  10,
			MaxBufferSize: 1,
			FlushInterval: time.Hour,
		}), nil
	}
	reg := ibexmetrics.NewProxy("usage-fact-ondrop")
	w := optionalUsageFactWriter("clickhouse://test", logger.Discard("billing"), reg, factory)
	if w == nil {
		t.Fatal("expected writer")
	}
	t.Cleanup(func() { _ = w.Shutdown(context.Background()) })

	first := sampleUsageFact("keep")
	second := sampleUsageFact("reject")
	if err := w.Write(first); err != nil {
		t.Fatalf("first write: %v", err)
	}
	if err := w.Write(second); err == nil {
		t.Fatal("expected buffer-full reject")
	}
	if got := usageFactRejectedTotal(t, reg); got != 1 {
		t.Fatalf("rejected metric=%v want 1", got)
	}
}

type stubUsageFactInserter struct{}

func (stubUsageFactInserter) InsertUsageFacts(context.Context, []billing.UsageFact) error {
	return nil
}
func (stubUsageFactInserter) Close() error { return nil }

func sampleUsageFact(requestID string) billing.UsageFact {
	return billing.UsageFact{
		RequestID:          requestID,
		OrgID:              uuid.MustParse("11111111-1111-4111-8111-111111111111"),
		AgentID:            uuid.MustParse("22222222-2222-4222-8222-222222222222"),
		Provider:           "openai",
		Model:              "gpt-4o",
		InputTokens:        1,
		OutputTokens:       1,
		TotalTokens:        2,
		EstimatedCostCents: 1,
		RateCardVersion:    "1",
		Completeness:       "complete",
		OccurredAt:         time.Now().UTC(),
	}
}

func usageFactRejectedTotal(t *testing.T, reg *ibexmetrics.ProxyRegistry) float64 {
	t.Helper()
	mfs, err := reg.Gatherer().Gather()
	if err != nil {
		t.Fatal(err)
	}
	for _, mf := range mfs {
		if mf.GetName() != "ibex_proxy_usage_fact_rejected_total" {
			continue
		}
		for _, m := range mf.GetMetric() {
			return m.GetCounter().GetValue()
		}
	}
	return 0
}

func TestUnit_WrapBudgetCacheErr(t *testing.T) {
	t.Parallel()
	if got := wrapBudgetCacheErr(nil); got != nil {
		t.Fatalf("nil err: got %v", got)
	}
	inner := errors.New("boom")
	got := wrapBudgetCacheErr(inner)
	if got == nil {
		t.Fatal("expected wrapped error")
	}
	if !errors.Is(got, inner) {
		t.Fatalf("wrapped=%v want Is(inner)", got)
	}
	if got.Error() != "budget cache: boom" {
		t.Fatalf("msg=%q", got.Error())
	}
}

func mustBudgetCache(t *testing.T) *billing.Cache {
	t.Helper()
	cache, err := billing.NewCache(
		fakeBudgetLoader{snap: billing.BudgetSnapshot{}},
		billing.Config{CacheTTL: time.Minute, LRUSize: 4},
		billing.NoopMetrics{},
	)
	if err != nil {
		t.Fatal(err)
	}
	return cache
}
