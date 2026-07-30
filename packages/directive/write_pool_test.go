package directive

import (
	"context"
	"errors"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func TestUnit_WritePool_TrySubmitDropsWhenFull(t *testing.T) {
	t.Parallel()

	started := make(chan struct{})
	var startOnce sync.Once
	release := make(chan struct{})
	var ran atomic.Int32
	p := newWritePool(1, 1, func(cacheWriteJob) {
		ran.Add(1)
		startOnce.Do(func() { close(started) })
		<-release
	})

	if !p.trySubmit(cacheWriteJob{key: "a"}) {
		t.Fatal("first submit should succeed")
	}
	waitClosed(t, started)
	if !p.trySubmit(cacheWriteJob{key: "b"}) {
		t.Fatal("queued submit should succeed")
	}
	if p.trySubmit(cacheWriteJob{key: "c"}) {
		t.Fatal("full queue should drop")
	}

	close(release)
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	if err := p.shutdown(ctx); err != nil {
		t.Fatalf("shutdown: %v", err)
	}
	if got := ran.Load(); got != 2 {
		t.Fatalf("ran=%d want 2", got)
	}
}

func TestUnit_WritePool_ShutdownRejectsSubmit(t *testing.T) {
	t.Parallel()

	var ran atomic.Int32
	p := newWritePool(1, 4, func(cacheWriteJob) { ran.Add(1) })

	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	if err := p.shutdown(ctx); err != nil {
		t.Fatalf("shutdown: %v", err)
	}
	if p.trySubmit(cacheWriteJob{key: "late"}) {
		t.Fatal("submit after shutdown should fail")
	}
	if ran.Load() != 0 {
		t.Fatalf("ran=%d want 0", ran.Load())
	}
}

func TestUnit_WritePool_ConcurrentSubmitDuringShutdown(t *testing.T) {
	t.Parallel()

	releaseWorkers := make(chan struct{})
	workerStarted := make(chan struct{}, 1)
	p := newWritePool(2, 8, func(cacheWriteJob) {
		select {
		case workerStarted <- struct{}{}:
		default:
		}
		<-releaseWorkers
	})

	if !p.trySubmit(cacheWriteJob{key: "seed"}) {
		t.Fatal("seed submit should succeed")
	}
	waitClosed(t, workerStarted)

	var wg sync.WaitGroup
	start := make(chan struct{})
	for i := 0; i < 32; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			<-start
			for j := 0; j < 100; j++ {
				_ = p.trySubmit(cacheWriteJob{key: "k"})
			}
		}()
	}

	shutdownDone := make(chan error, 1)
	go func() {
		ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		defer cancel()
		shutdownDone <- p.shutdown(ctx)
	}()

	close(start)
	wg.Wait()
	close(releaseWorkers)
	if err := <-shutdownDone; err != nil {
		t.Fatalf("shutdown: %v", err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	if err := p.shutdown(ctx); err != nil {
		t.Fatalf("idempotent shutdown: %v", err)
	}
	if p.trySubmit(cacheWriteJob{key: "after"}) {
		t.Fatal("submit after shutdown should fail")
	}
}

func TestUnit_WritePool_NilReceiver(t *testing.T) {
	t.Parallel()

	var p *writePool
	if p.trySubmit(cacheWriteJob{key: "x"}) {
		t.Fatal("nil pool should reject submit")
	}
	if err := p.shutdown(context.Background()); err != nil {
		t.Fatalf("nil shutdown: %v", err)
	}
}

func TestUnit_WritePool_DefaultsAndNilHandler(t *testing.T) {
	t.Parallel()

	var ran atomic.Int32
	p := newWritePool(0, 0, func(cacheWriteJob) { ran.Add(1) })
	if !p.trySubmit(cacheWriteJob{key: "a"}) {
		t.Fatal("expected submit with default queue")
	}

	nilHandler := newWritePool(1, 1, nil)
	if !nilHandler.trySubmit(cacheWriteJob{key: "b"}) {
		t.Fatal("expected submit with nil handler")
	}

	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	if err := p.shutdown(ctx); err != nil {
		t.Fatalf("shutdown p: %v", err)
	}
	if err := nilHandler.shutdown(ctx); err != nil {
		t.Fatalf("shutdown nilHandler: %v", err)
	}
	if got := ran.Load(); got != 1 {
		t.Fatalf("ran=%d want 1", got)
	}
}

func TestUnit_WritePool_ShutdownTimeout(t *testing.T) {
	t.Parallel()

	release := make(chan struct{})
	p := newWritePool(1, 1, func(cacheWriteJob) { <-release })
	if !p.trySubmit(cacheWriteJob{key: "block"}) {
		t.Fatal("expected submit")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Millisecond)
	defer cancel()
	if err := p.shutdown(ctx); !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("err=%v want deadline exceeded", err)
	}
	close(release)

	drainCtx, drainCancel := context.WithTimeout(context.Background(), time.Second)
	defer drainCancel()
	if err := p.shutdown(drainCtx); err != nil {
		t.Fatalf("drain shutdown: %v", err)
	}
}

func waitClosed(t *testing.T, ch <-chan struct{}) {
	t.Helper()
	select {
	case <-ch:
	case <-time.After(2 * time.Second):
		t.Fatal("timeout waiting for worker start")
	}
}
