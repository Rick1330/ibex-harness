package redissub_test

import (
	"context"
	"errors"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/redissub"
	"github.com/stretchr/testify/require"
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

	require.Eventually(t, func() bool { return calls.Load() >= 1 }, 2*time.Second, 10*time.Millisecond)
	loop.Stop()
	cancel()
	select {
	case <-done:
	case <-time.After(3 * time.Second):
		t.Fatal("Run did not exit")
	}
}

func TestUnit_LoopCtxCancelExits(t *testing.T) {
	t.Parallel()
	log, err := logger.New(logger.Config{Service: "redissub-test"})
	if err != nil {
		t.Fatalf("logger: %v", err)
	}
	loop := redissub.NewLoop()
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{})
	go func() {
		defer close(done)
		loop.Run(ctx, log, "test", func(context.Context) (bool, error) {
			return true, errors.New("session end")
		})
	}()
	cancel()
	select {
	case <-done:
	case <-time.After(3 * time.Second):
		t.Fatal("Run did not exit on cancel")
	}
	if !loop.Stopped(ctx) {
		t.Fatal("expected Stopped after cancel")
	}
}

func TestUnit_LoopStoppedAndSleepBackoff(t *testing.T) {
	t.Parallel()
	log, err := logger.New(logger.Config{Service: "redissub-test"})
	if err != nil {
		t.Fatalf("logger: %v", err)
	}
	loop := redissub.NewLoop()
	ctx := context.Background()
	if loop.Stopped(ctx) {
		t.Fatal("unexpected stopped")
	}
	var calls atomic.Int64
	done := make(chan struct{})
	go func() {
		defer close(done)
		loop.Run(ctx, log, "test", func(context.Context) (bool, error) {
			calls.Add(1)
			return false, errors.New("fail")
		})
	}()
	require.Eventually(t, func() bool { return calls.Load() >= 1 }, 2*time.Second, 10*time.Millisecond)
	loop.Stop()
	select {
	case <-done:
	case <-time.After(3 * time.Second):
		t.Fatal("Run did not exit after Stop during backoff")
	}
	if !loop.Stopped(ctx) {
		t.Fatal("expected stopped")
	}
}
