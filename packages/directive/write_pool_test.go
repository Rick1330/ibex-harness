package directive

import (
	"context"
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

func waitClosed(t *testing.T, ch <-chan struct{}) {
	t.Helper()
	select {
	case <-ch:
	case <-time.After(2 * time.Second):
		t.Fatal("timeout waiting for worker start")
	}
}
