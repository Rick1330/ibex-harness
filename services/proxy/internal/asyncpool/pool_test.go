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
	entered := make(chan struct{}, 2)
	release := make(chan struct{})

	p := mustPool(t, 2, 8)
	cleanupPool(t, p)

	const tasks = 20
	var wg sync.WaitGroup
	wg.Add(tasks)
	go submitConcurrencyTasks(t, concurrencySubmit{
		pool: p, tasks: tasks, wg: &wg,
		running: &running, maxRunning: &maxRunning,
		entered: entered, release: release,
	})

	<-entered
	<-entered
	close(release)
	wg.Wait()

	if maxRunning.Load() > 2 {
		t.Fatalf("max concurrent=%d want <=2", maxRunning.Load())
	}
}

func mustPool(t *testing.T, workers, queue int) *asyncpool.Pool {
	t.Helper()
	p, err := asyncpool.New(workers, queue, nil)
	if err != nil {
		t.Fatal(err)
	}
	return p
}

func cleanupPool(t *testing.T, p *asyncpool.Pool) {
	t.Helper()
	t.Cleanup(func() {
		if err := p.Shutdown(context.Background()); err != nil {
			t.Errorf("shutdown: %v", err)
		}
	})
}

type concurrencySubmit struct {
	pool                *asyncpool.Pool
	tasks               int
	wg                  *sync.WaitGroup
	running, maxRunning *atomic.Int32
	entered             chan<- struct{}
	release             <-chan struct{}
}

func submitConcurrencyTasks(t *testing.T, s concurrencySubmit) {
	t.Helper()
	for i := 0; i < s.tasks; i++ {
		if !s.pool.Submit(concurrencyTask(s)) {
			t.Error("submit rejected")
			s.wg.Done()
		}
	}
}

func concurrencyTask(s concurrencySubmit) func() {
	return func() {
		defer s.wg.Done()
		recordPeak(s.running, s.maxRunning)
		signalEntered(s.entered)
		<-s.release
		s.running.Add(-1)
	}
}

func recordPeak(running, maxRunning *atomic.Int32) {
	n := running.Add(1)
	for {
		cur := maxRunning.Load()
		if n <= cur || maxRunning.CompareAndSwap(cur, n) {
			return
		}
	}
}

func signalEntered(entered chan<- struct{}) {
	select {
	case entered <- struct{}{}:
	default:
	}
}

func TestUnit_Pool_SubmitBlocksWhenFull(t *testing.T) {
	t.Parallel()

	gate := make(chan struct{})
	p := mustPool(t, 1, 1)
	cleanupPool(t, p)

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
}

func TestUnit_Pool_ShutdownDrains(t *testing.T) {
	t.Parallel()

	var ran atomic.Int32
	started := make(chan struct{}, 10)
	release := make(chan struct{})

	p, err := asyncpool.New(2, 16, nil)
	if err != nil {
		t.Fatal(err)
	}

	for i := 0; i < 10; i++ {
		if !p.Submit(func() {
			started <- struct{}{}
			<-release
			ran.Add(1)
		}) {
			t.Fatal("submit")
		}
	}
	for i := 0; i < 2; i++ {
		<-started
	}
	close(release)

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

	if err := p.Shutdown(context.Background()); err != nil {
		t.Fatalf("shutdown: %v", err)
	}

	mu.Lock()
	defer mu.Unlock()
	if len(depths) == 0 {
		t.Fatal("expected depth reports")
	}
}

func TestUnit_Pool_TrySubmitNonBlocking(t *testing.T) {
	t.Parallel()

	gate := make(chan struct{})
	p := mustPool(t, 1, 1)
	cleanupPool(t, p)

	started := make(chan struct{})
	if !p.Submit(func() {
		close(started)
		<-gate
	}) {
		t.Fatal("first submit")
	}
	<-started
	if !p.Submit(func() {}) {
		t.Fatal("queue slot")
	}
	if p.TrySubmit(func() {}) {
		t.Fatal("TrySubmit must fail when full")
	}
	close(gate)
}

func TestUnit_Pool_TrySubmitAfterShutdown(t *testing.T) {
	t.Parallel()
	p, err := asyncpool.New(1, 1, nil)
	if err != nil {
		t.Fatal(err)
	}
	if err := p.Shutdown(context.Background()); err != nil {
		t.Fatal(err)
	}
	if p.TrySubmit(func() {}) {
		t.Fatal("TrySubmit after shutdown must fail")
	}
}

func TestUnit_Pool_TrySubmitShutdownRace(t *testing.T) {
	t.Parallel()
	// Stress admission vs close: must never panic (send on closed channel).
	const rounds = 200
	for i := 0; i < rounds; i++ {
		p := mustPool(t, 2, 4)
		var wg sync.WaitGroup
		wg.Add(2)
		go func() {
			defer wg.Done()
			for j := 0; j < 64; j++ {
				_ = p.TrySubmit(func() {})
			}
		}()
		go func() {
			defer wg.Done()
			_ = p.Shutdown(context.Background())
		}()
		wg.Wait()
		if p.TrySubmit(func() {}) {
			t.Fatal("TrySubmit after shutdown must fail")
		}
	}
}
