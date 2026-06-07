package shutdown

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"os"
	"sync/atomic"
	"syscall"
	"testing"
	"time"
)

func testLogger() *slog.Logger {
	return slog.New(slog.NewTextHandler(io.Discard, nil))
}

func TestCoordinator_CleanShutdown(t *testing.T) {
	sigCh := make(chan os.Signal, 1)
	coord := NewWithSignalChan(5*time.Second, testLogger(), sigCh)
	var order []int
	coord.Register(func(ctx context.Context) error {
		order = append(order, 1)
		return nil
	})
	coord.Register(func(ctx context.Context) error {
		order = append(order, 2)
		return nil
	})

	go func() {
		sigCh <- syscall.SIGTERM
	}()

	if err := coord.Wait(); err != nil {
		t.Fatalf("Wait: %v", err)
	}
	if len(order) != 2 {
		t.Fatalf("handler count: %d", len(order))
	}
	if order[0] != 1 {
		t.Fatalf("first handler: %d", order[0])
	}
	if order[1] != 2 {
		t.Fatalf("second handler: %d", order[1])
	}
}

func TestCoordinator_TimeoutExceeded(t *testing.T) {
	sigCh := make(chan os.Signal, 1)
	coord := NewWithSignalChan(50*time.Millisecond, testLogger(), sigCh)
	coord.Register(func(ctx context.Context) error {
		select {
		case <-time.After(200 * time.Millisecond):
			return nil
		case <-ctx.Done():
			return ctx.Err()
		}
	})

	go func() {
		sigCh <- syscall.SIGTERM
	}()

	if err := coord.Wait(); err == nil {
		t.Fatal("expected timeout error")
	}
}

func TestCoordinator_HandlerError(t *testing.T) {
	sigCh := make(chan os.Signal, 1)
	coord := NewWithSignalChan(5*time.Second, testLogger(), sigCh)
	handlerErr := errors.New("close failed")
	var ranSecond atomic.Bool
	coord.Register(func(ctx context.Context) error {
		return handlerErr
	})
	coord.Register(func(ctx context.Context) error {
		ranSecond.Store(true)
		return nil
	})

	go func() {
		sigCh <- syscall.SIGTERM
	}()

	if err := coord.Wait(); err != nil {
		t.Fatalf("Wait: %v", err)
	}
	if !ranSecond.Load() {
		t.Fatal("second handler should run after first handler error")
	}
}

func TestCoordinator_SIGINTImmediate(t *testing.T) {
	sigCh := make(chan os.Signal, 1)
	coord := NewWithSignalChan(30*time.Second, testLogger(), sigCh)
	var start time.Time
	coord.Register(func(ctx context.Context) error {
		start = time.Now()
		if ctx.Err() == nil {
			t.Fatal("expected expired drain context on SIGINT")
		}
		return nil
	})

	go func() {
		sigCh <- syscall.SIGINT
	}()

	if err := coord.Wait(); err != nil {
		t.Fatalf("Wait: %v", err)
	}
	if time.Since(start) > 100*time.Millisecond {
		t.Fatal("SIGINT shutdown should not wait for drain timeout")
	}
}
