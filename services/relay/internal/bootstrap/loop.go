package bootstrap

import (
	"context"
	"fmt"
	"math/rand/v2"
	"time"

	"github.com/Rick1330/ibex-harness/packages/evidenceoutbox"
	"github.com/Rick1330/ibex-harness/packages/logger"
	ibexmetrics "github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/services/relay/internal/config"
	"go.opentelemetry.io/otel"
)

// loopMaxBackoff caps the consecutive-failure backoff between poll cycles.
const loopMaxBackoff = time.Minute

// tracerName labels relay dependency spans.
const tracerName = "ibex-relay"

// batchRelay is the relay surface the poll loop depends on.
type batchRelay interface {
	ProcessBatch(ctx context.Context) (evidenceoutbox.RelayBatchResult, error)
	RecoverInFlight(ctx context.Context, olderThan time.Duration) (int64, error)
}

type loopDeps struct {
	relay   batchRelay
	metrics *ibexmetrics.RelayRegistry
	log     *logger.Logger
	cfg     config.Config
}

// runLoop polls claim/recover/deliver cycles until ctx is canceled. Transient
// failures back off exponentially (bounded by loopMaxBackoff) so a down
// dependency is retried without hot-looping.
func runLoop(ctx context.Context, deps loopDeps) {
	deps.log.InfoCtx(ctx, "relay loop starting",
		"poll_interval", deps.cfg.PollInterval.String(),
		"batch_size", deps.cfg.BatchSize,
		"max_attempts", deps.cfg.MaxAttempts,
		"recover_after", deps.cfg.RecoverAfter.String(),
		"operation_timeout", deps.cfg.OperationTimeout.String())
	backoff := deps.cfg.ErrorBackoff
	for ctx.Err() == nil {
		err := runOnce(ctx, deps)
		if ctx.Err() != nil {
			break
		}
		wait := deps.cfg.PollInterval
		if err != nil {
			deps.log.ErrorCtx(ctx, "relay cycle failed", "error", err, "backoff", backoff.String())
			wait = withJitter(backoff)
			backoff = doubleBackoff(backoff)
		} else {
			backoff = deps.cfg.ErrorBackoff
		}
		if !sleepUntil(ctx, wait) {
			break
		}
	}
	deps.log.InfoCtx(context.Background(), "relay loop stopped")
}

// runOnce performs one recover + claim + deliver cycle bounded by the
// configured operation timeout.
func runOnce(ctx context.Context, deps loopDeps) error {
	opCtx, cancel := context.WithTimeout(ctx, deps.cfg.OperationTimeout)
	defer cancel()

	recoverCtx, recoverSpan := otel.Tracer(tracerName).Start(opCtx, "relay.recover_in_flight")
	recovered, err := deps.relay.RecoverInFlight(recoverCtx, deps.cfg.RecoverAfter)
	recoverSpan.End()
	if err != nil {
		return fmt.Errorf("recover in-flight: %w", err)
	}
	if recovered > 0 {
		deps.metrics.AddRecovered(int(recovered))
		deps.log.WarnCtx(ctx, "recovered stale in-flight rows", "count", recovered)
	}

	start := time.Now()
	batchCtx, batchSpan := otel.Tracer(tracerName).Start(opCtx, "relay.process_batch")
	result, err := deps.relay.ProcessBatch(batchCtx)
	batchSpan.End()
	batchResult := ibexmetrics.RelayBatchOK
	if err != nil {
		batchResult = ibexmetrics.RelayBatchError
	}
	deps.metrics.ObserveBatch(batchResult, time.Since(start).Seconds())
	// ProcessBatch returns the counts it completed before an error; record them
	// so a partial failure does not hide delivered/dead-lettered work.
	deps.metrics.AddClaimed(result.Claimed)
	deps.metrics.AddDelivered(result.Delivered)
	deps.metrics.AddRetried(result.Failed)
	deps.metrics.AddDeadLettered(result.Poisoned)
	if err != nil {
		return fmt.Errorf("process batch: %w", err)
	}
	if result.Claimed > 0 {
		deps.log.InfoCtx(ctx, "relay batch processed",
			"claimed", result.Claimed,
			"delivered", result.Delivered,
			"retried", result.Failed,
			"dead_lettered", result.Poisoned)
	}
	return nil
}

// withJitter returns a bounded random duration in [d/2, d) so relays started
// together do not retry a shared dependency outage in lockstep.
func withJitter(d time.Duration) time.Duration {
	if d <= 1 {
		return d
	}
	half := d / 2
	return half + time.Duration(rand.Int64N(int64(half)))
}

func doubleBackoff(v time.Duration) time.Duration {
	if v <= 0 {
		return loopMaxBackoff
	}
	v *= 2
	if v > loopMaxBackoff {
		return loopMaxBackoff
	}
	return v
}

// sleepUntil returns false when ctx is canceled before the wait elapses.
func sleepUntil(ctx context.Context, wait time.Duration) bool {
	if wait <= 0 {
		return ctx.Err() == nil
	}
	timer := time.NewTimer(wait)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return false
	case <-timer.C:
		return true
	}
}
