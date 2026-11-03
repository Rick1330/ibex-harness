package bootstrap

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"sync/atomic"
	"time"

	"github.com/Rick1330/ibex-harness/packages/healthcheck"
	ibexmetrics "github.com/Rick1330/ibex-harness/packages/metrics"
)

const (
	httpReadHeaderTimeout = 5 * time.Second
	httpReadTimeout       = 10 * time.Second
	httpWriteTimeout      = 10 * time.Second
	httpIdleTimeout       = 90 * time.Second
)

// newRelayHTTPServer builds the health/readiness/metrics surface. Postgres and
// ClickHouse are both critical: the daemon must fail closed when either
// authoritative dependency is unreachable.
func newRelayHTTPServer(port string, rt *runtime, reg *ibexmetrics.RelayRegistry, draining *atomic.Bool) *http.Server {
	healthSrv := &healthcheck.Server{
		CriticalCheckers: map[string]healthcheck.Checker{
			"postgres":   healthcheck.PostgresSelect1(rt.db),
			"clickhouse": clickHousePingChecker(rt),
			"draining":   drainingChecker(draining),
		},
	}
	mux := http.NewServeMux()
	mux.HandleFunc("/health", healthSrv.HealthHandler())
	mux.HandleFunc("/ready", healthSrv.ReadyHandler())
	mux.Handle("/metrics", ibexmetrics.Handler(reg.Gatherer()))
	return &http.Server{
		Addr:              ":" + port,
		Handler:           mux,
		ReadHeaderTimeout: httpReadHeaderTimeout,
		ReadTimeout:       httpReadTimeout,
		WriteTimeout:      httpWriteTimeout,
		IdleTimeout:       httpIdleTimeout,
	}
}

func clickHousePingChecker(rt *runtime) healthcheck.Checker {
	return func(ctx context.Context) error {
		if rt == nil || rt.sink == nil {
			return errors.New("clickhouse sink not configured")
		}
		if err := rt.sink.Ping(ctx); err != nil {
			return fmt.Errorf("clickhouse unreachable: %w", err)
		}
		return nil
	}
}

// drainingChecker flips readiness unhealthy as soon as shutdown starts so
// load balancers stop routing to the draining daemon.
func drainingChecker(draining *atomic.Bool) healthcheck.Checker {
	return func(context.Context) error {
		if draining.Load() {
			return errors.New("shutdown in progress")
		}
		return nil
	}
}
