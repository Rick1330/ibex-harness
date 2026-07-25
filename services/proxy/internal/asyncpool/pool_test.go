package asyncpool_test

import (
	"context"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/services/proxy/internal/asyncpool"
)

func TestUnit_Pool_ConcurrencyBound(t *testing.T) {
	t.Parallel()
	var running, maxRunning atomic.Int32
	p, err := asyncpool.New(2, 8, nil)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = p.Shutdown(context.Background()) }()

	var wg sync.WaitGroup
	for i := 0; i < 20; i++ {
		wg.Add(1)
		ok := p.Submit(func() {
			defer wg.Done()
			n := running.Add(1)
			for {
				cur := maxRunning.Load()
				if n <= cur || maxRunning.CompareAndSwap(cur, n) {
					break
				}
			}
			time.Sleep(5 * time.Millisecond)
			running.Add(-1)
		})
		if !ok {
			t.Fatal("submit rejected")
		}
	}
	wg.Wait()
	if maxRunning.Load() > 2 {
		t.Fatalf("max concurrent=%d want <=2", maxRunning.Load())
	}
}

func TestUnit_Pool_SubmitBlocksWhenFull(t *testing.T) {
	t.Parallel()
	gate := make(chan struct{})
	p, err := asyncpool.New(1, 1, nil)
	if err != nil {
		t.Fatal(err)
	}

	started := make(chan struct{})
	if !p.Submit(func() {
		close(started)
		<-gate
	}) {
		t.Fatal("first submit")
	}
	<-started
	if !p.Submit(func() {}) {
		t.Fatal("queue slot submit")
	}

	unblocked := make(chan struct{})
	go func() {
		_ = p.Submit(func() {})
		close(unblocked)
	}()
	select {
	case <-unblocked:
		t.Fatal("submit should block when queue full")
	case <-time.After(40 * time.Millisecond):
	}
	close(gate)
	select {
	case <-unblocked:
	case <-time.After(2 * time.Second):
		t.Fatal("submit did not unblock")
	}
	_ = p.Shutdown(context.Background())
}

func TestUnit_Pool_ShutdownDrains(t *testing.T) {
	t.Parallel()
	var ran atomic.Int32
	p, err := asyncpool.New(2, 16, nil)
	if err != nil {
		t.Fatal(err)
	}
	for i := 0; i < 10; i++ {
		if !p.Submit(func() {
			time.Sleep(5 * time.Millisecond)
			ran.Add(1)
		}) {
			t.Fatal("submit")
		}
	}
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	if err := p.Shutdown(ctx); err != nil {
		t.Fatalf("shutdown: %v", err)
	}
	if ran.Load() != 10 {
		t.Fatalf("ran=%d want 10", ran.Load())
	}
	if p.Submit(func() {}) {
		t.Fatal("submit after shutdown should fail")
	}
}

func TestUnit_Pool_DepthHook(t *testing.T) {
	t.Parallel()
	var depths []float64
	var mu sync.Mutex
	p, err := asyncpool.New(1, 4, func(d float64) {
		mu.Lock()
		depths = append(depths, d)
		mu.Unlock()
	})
	if err != nil {
		t.Fatal(err)
	}
	block := make(chan struct{})
	if !p.Submit(func() { <-block }) {
		t.Fatal("submit")
	}
	if !p.Submit(func() {}) {
		t.Fatal("submit queued")
	}
	close(block)
	_ = p.Shutdown(context.Background())
	mu.Lock()
	defer mu.Unlock()
	if len(depths) == 0 {
		t.Fatal("expected depth reports")
	}
}

func TestUnit_Pool_InvalidArgs(t *testing.T) {
	t.Parallel()
	if _, err := asyncpool.New(0, 1, nil); err == nil {
		t.Fatal("expected workers error")
	}
	if _, err := asyncpool.New(1, 0, nil); err == nil {
		t.Fatal("expected queue error")
	}
}
