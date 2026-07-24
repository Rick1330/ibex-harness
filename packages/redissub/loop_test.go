package redissub_test

import (
	"context"
	"errors"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/redissub"
)

func TestUnit_LoopStopBeforeRun(t *testing.T) {
	t.Parallel()
	loop := redissub.NewLoop()
	loop.Stop()
	select {
	case <-loop.StopCh():
	default:
		t.Fatal("expected stop channel closed")
	}
}

func TestUnit_LoopRunReconnectThenStop(t *testing.T) {
	t.Parallel()
	log, err := logger.New(logger.Config{Service: "redissub-test"})
	if err != nil {
		t.Fatalf("logger: %v", err)
	}
	loop := redissub.NewLoop()
	var calls atomic.Int64
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	done := make(chan struct{})
	go func() {
		defer close(done)
		loop.Run(ctx, log, "test", func(context.Context) (bool, error) {
			n := calls.Add(1)
			if n == 1 {
				return false, errors.New("first fail")
			}
			<-loop.StopCh()
			return true, nil
		})
	}()

	waitUntil(t, 2*time.Second, func() bool { return calls.Load() >= 1 })
	loop.Stop()
	cancel()
	select {
	case <-done:
	case <-time.After(3 * time.Second):
		t.Fatal("Run did not exit")
	}
}

func waitUntil(t *testing.T, d time.Duration, ok func() bool) {
	t.Helper()
	deadline := time.Now().Add(d)
	for time.Now().Before(deadline) {
		if ok() {
			return
		}
		time.Sleep(10 * time.Millisecond)
	}
	t.Fatal("timeout")
}
