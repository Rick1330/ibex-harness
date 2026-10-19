package bootstrap

import (
	"context"
	"errors"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/evidenceoutbox"
	"github.com/Rick1330/ibex-harness/packages/logger"
	ibexmetrics "github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/services/relay/internal/config"
)

type stubRelay struct {
	recoverN     int64
	recoverErr   error
	recoverOlder time.Duration
	batchResult  evidenceoutbox.RelayBatchResult
	batchErr     error
	batchCalls   atomic.Int64
	recoverCalls atomic.Int64
}

func (s *stubRelay) ProcessBatch(context.Context) (evidenceoutbox.RelayBatchResult, error) {
	s.batchCalls.Add(1)
	return s.batchResult, s.batchErr
}

func (s *stubRelay) RecoverInFlight(_ context.Context, olderThan time.Duration) (int64, error) {
	s.recoverCalls.Add(1)
	s.recoverOlder = olderThan
	return s.recoverN, s.recoverErr
}

func loopTestDeps(stub *stubRelay) (loopDeps, *ibexmetrics.RelayRegistry) {
	reg := ibexmetrics.NewRelay("test-relay")
	return loopDeps{
		relay:   stub,
		metrics: reg,
		log:     logger.Discard("relay-test"),
		cfg: config.Config{
			PollInterval:     time.Millisecond,
			BatchSize:        1,
			MaxAttempts:      1,
			RecoverAfter:     time.Second,
			OperationTimeout: time.Second,
			ErrorBackoff:     time.Millisecond,
		},
	}, reg
}

func TestRunOnce_RecordsBatchOutcome(t *testing.T) {
	stub := &stubRelay{
		recoverN:    2,
		batchResult: evidenceoutbox.RelayBatchResult{Claimed: 3, Delivered: 2, Failed: 1, Poisoned: 0},
	}
	deps, reg := loopTestDeps(stub)
	if err := runOnce(context.Background(), deps); err != nil {
		t.Fatalf("runOnce: %v", err)
	}
	if stub.recoverOlder != time.Second {
		t.Fatalf("recover olderThan: got %s", stub.recoverOlder)
	}
	for name, want := range map[string]float64{
		"ibex_relay_claimed_total":     3,
		"ibex_relay_delivered_total":   2,
		"ibex_relay_retried_total":     1,
		"ibex_relay_recovered_total":   2,
		"ibex_relay_dead_letter_total": 0,
	} {
		if got := metricValue(t, reg, name); got != want {
			t.Fatalf("%s: got %v want %v", name, got, want)
		}
	}
	if got := metricSeriesCount(t, reg, "ibex_relay_batch_duration_seconds"); got != 1 {
		t.Fatalf("batch duration series: %d", got)
	}
}

func TestRunOnce_RecoverFailureSkipsBatch(t *testing.T) {
	stub := &stubRelay{recoverErr: errors.New("db down")}
	deps, _ := loopTestDeps(stub)
	if err := runOnce(context.Background(), deps); err == nil {
		t.Fatal("recover failure must surface")
	}
	if stub.batchCalls.Load() != 0 {
		t.Fatalf("batch must not run after recover failure, calls=%d", stub.batchCalls.Load())
	}
}

func TestRunOnce_BatchFailureRecordsErrorResult(t *testing.T) {
	stub := &stubRelay{batchErr: errors.New("claim failed")}
	deps, reg := loopTestDeps(stub)
	if err := runOnce(context.Background(), deps); err == nil {
		t.Fatal("batch failure must surface")
	}
	if stub.batchCalls.Load() != 1 {
		t.Fatalf("batch calls: %d", stub.batchCalls.Load())
	}
	if got := metricSeriesCount(t, reg, "ibex_relay_batches_total"); got != 1 {
		t.Fatalf("batch result series: %d", got)
	}
}

func TestRunLoop_StopsWhenContextCanceled(t *testing.T) {
	stub := &stubRelay{}
	deps, _ := loopTestDeps(stub)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	runLoop(ctx, deps)
	if stub.batchCalls.Load() != 0 || stub.recoverCalls.Load() != 0 {
		t.Fatalf("canceled loop must not run cycles: batch=%d recover=%d", stub.batchCalls.Load(), stub.recoverCalls.Load())
	}
}

func TestRunLoop_ExitsAfterCancelDuringPoll(t *testing.T) {
	stub := &stubRelay{}
	deps, _ := loopTestDeps(stub)
	deps.cfg.PollInterval = time.Hour
	cancel, done := startRelayLoop(t, deps)
	waitFor(t, func() bool { return stub.batchCalls.Load() == 1 })
	stopRelayLoop(t, cancel, done)
}

// startRelayLoop runs runLoop in a goroutine and returns its cancel func and a
// channel closed when the loop returns.
func startRelayLoop(t *testing.T, deps loopDeps) (context.CancelFunc, <-chan struct{}) {
	t.Helper()
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{})
	go func() {
		defer close(done)
		runLoop(ctx, deps)
	}()
	return cancel, done
}

func stopRelayLoop(t *testing.T, cancel context.CancelFunc, done <-chan struct{}) {
	t.Helper()
	cancel()
	select {
	case <-done:
	case <-time.After(5 * time.Second):
		t.Fatal("loop did not stop after cancel")
	}
}

func metricSeriesCount(t *testing.T, reg *ibexmetrics.RelayRegistry, name string) int {
	t.Helper()
	mfs, err := reg.Gatherer().Gather()
	if err != nil {
		t.Fatal(err)
	}
	for _, mf := range mfs {
		if mf.GetName() == name {
			return len(mf.GetMetric())
		}
	}
	return 0
}

func metricValue(t *testing.T, reg *ibexmetrics.RelayRegistry, name string) float64 {
	t.Helper()
	mfs, err := reg.Gatherer().Gather()
	if err != nil {
		t.Fatal(err)
	}
	for _, mf := range mfs {
		if mf.GetName() != name {
			continue
		}
		metrics := mf.GetMetric()
		if len(metrics) != 1 {
			t.Fatalf("%s: got %d series want 1", name, len(metrics))
		}
		if c := metrics[0].GetCounter(); c != nil {
			return c.GetValue()
		}
		if g := metrics[0].GetGauge(); g != nil {
			return g.GetValue()
		}
		t.Fatalf("%s: unsupported metric type", name)
	}
	t.Fatalf("metric %s not found", name)
	return 0
}

func waitFor(t *testing.T, cond func() bool) {
	t.Helper()
	deadline := time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline) {
		if cond() {
			return
		}
		time.Sleep(time.Millisecond)
	}
	t.Fatal("condition not reached")
}

func TestRunOnce_PartialBatchRecordsCompletedWork(t *testing.T) {
	stub := &stubRelay{
		batchResult: evidenceoutbox.RelayBatchResult{Claimed: 2, Delivered: 1, Failed: 1},
		batchErr:    errors.New("finalize failed"),
	}
	deps, reg := loopTestDeps(stub)
	if err := runOnce(context.Background(), deps); err == nil {
		t.Fatal("batch error must surface")
	}
	for name, want := range map[string]float64{
		"ibex_relay_claimed_total":   2,
		"ibex_relay_delivered_total": 1,
		"ibex_relay_retried_total":   1,
	} {
		if got := metricValue(t, reg, name); got != want {
			t.Fatalf("%s: got %v want %v", name, got, want)
		}
	}
	if got := metricSeriesCount(t, reg, "ibex_relay_batches_total"); got != 1 {
		t.Fatalf("batch result series: %d", got)
	}
}

func TestWithJitter_WithinBounds(t *testing.T) {
	d := 10 * time.Second
	for i := 0; i < 200; i++ {
		got := withJitter(d)
		if got < d/2 || got >= d {
			t.Fatalf("withJitter(%s) = %s, want [%s, %s)", d, got, d/2, d)
		}
	}
	if got := withJitter(0); got != 0 {
		t.Fatalf("withJitter(0) = %s, want 0", got)
	}
	if got := withJitter(time.Nanosecond); got != time.Nanosecond {
		t.Fatalf("withJitter(ns) = %s, want 1ns", got)
	}
}

func TestDoubleBackoff(t *testing.T) {
	if got := doubleBackoff(time.Second); got != 2*time.Second {
		t.Fatalf("got %s", got)
	}
	if got := doubleBackoff(50 * time.Second); got != loopMaxBackoff {
		t.Fatalf("cap: got %s", got)
	}
	if got := doubleBackoff(0); got != loopMaxBackoff {
		t.Fatalf("zero: got %s", got)
	}
}

func TestRunLoop_BacksOffAfterFailureAndStopsOnCancel(t *testing.T) {
	stub := &stubRelay{batchErr: errors.New("claim failed")}
	deps, _ := loopTestDeps(stub)
	deps.cfg.ErrorBackoff = time.Millisecond
	deps.cfg.PollInterval = time.Millisecond
	cancel, done := startRelayLoop(t, deps)
	waitFor(t, func() bool { return stub.batchCalls.Load() >= 3 })
	stopRelayLoop(t, cancel, done)
}
