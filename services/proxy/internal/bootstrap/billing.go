package bootstrap

import (
	"context"
	"database/sql"
	"fmt"

	"github.com/Rick1330/ibex-harness/packages/billing"
	"github.com/Rick1330/ibex-harness/packages/logger"
	ibexmetrics "github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/redis/go-redis/v9"
)

type budgetMetricsAdapter struct {
	reg *ibexmetrics.ProxyRegistry
}

func (a budgetMetricsAdapter) IncCacheHit(tier string) {
	a.reg.IncBudgetCacheHit(tier)
}
func (a budgetMetricsAdapter) IncCacheMiss(tier string) {
	a.reg.IncBudgetCacheMiss(tier)
}
func (a budgetMetricsAdapter) IncDeny() {
	a.reg.IncBudgetDeny()
}
func (a budgetMetricsAdapter) IncInvalidate() {
	a.reg.IncBudgetInvalidate()
}
func (a budgetMetricsAdapter) SetLRUSize(n float64) {
	a.reg.SetBudgetLRUSize(n)
}

func billingMetrics(reg *ibexmetrics.ProxyRegistry) billing.Metrics {
	if reg != nil {
		return budgetMetricsAdapter{reg: reg}
	}
	return billing.NoopMetrics{}
}

func newBudgetCache(pgDB *sql.DB, reg *ibexmetrics.ProxyRegistry) (*billing.Cache, error) {
	if pgDB == nil {
		return nil, nil
	}
	store, err := billing.NewStore(pgDB)
	if err != nil {
		return nil, err
	}
	return billing.NewCache(store, billing.Config{}, billingMetrics(reg))
}

func startBudgetSubscriber(
	redisClient redis.UniversalClient,
	cache *billing.Cache,
	log *logger.Logger,
	reg *ibexmetrics.ProxyRegistry,
) (*billing.Subscriber, context.CancelFunc, error) {
	if redisClient == nil || cache == nil {
		return nil, nil, nil
	}
	sub, err := billing.NewSubscriber(redisClient, cache, log, billingMetrics(reg))
	if err != nil {
		return nil, nil, err
	}
	ctx, cancel := context.WithCancel(context.Background())
	go sub.Run(ctx)
	if log != nil {
		log.InfoCtx(context.Background(), "budget subscriber started", "pattern", billing.ChannelPattern)
	}
	return sub, cancel, nil
}

func optionalUsageFactWriter(
	cfgDSN string,
	log *logger.Logger,
) *billing.UsageFactWriter {
	if cfgDSN == "" {
		return nil
	}
	w, err := billing.NewUsageFactWriter(billing.UsageFactConfig{DSN: cfgDSN})
	if err != nil {
		if log != nil {
			log.WarnCtx(context.Background(), "usage fact writer disabled", "error", err)
		}
		return nil
	}
	return w
}

func wrapBudgetCacheErr(err error) error {
	if err == nil {
		return nil
	}
	return fmt.Errorf("budget cache: %w", err)
}
