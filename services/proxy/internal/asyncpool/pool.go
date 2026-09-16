// Package asyncpool provides a bounded, non-dropping worker pool for
// post-response work (session checkpoints). When the queue is full, Submit
// blocks the caller rather than dropping tasks.
package asyncpool

import (
	"context"
	"fmt"
	"sync"
	"sync/atomic"
)

// DepthFunc reports the current number of queued (not yet started) jobs.
type DepthFunc func(depth float64)

// Pool is a fixed-worker, buffered-queue executor.
type Pool struct {
	jobs     chan func()
	quit     chan struct{}
	wg       sync.WaitGroup
	submitWG sync.WaitGroup
	// gate serializes closed+quit with submitWG.Add so Wait never races Add.
	gate sync.Mutex
	// sendMu serializes TrySubmit's non-blocking send with close(jobs).
	sendMu    sync.Mutex
	depth     DepthFunc
	closed    atomic.Bool
	drained   chan struct{}
	drainOnce sync.Once
}

// New constructs a pool with the given worker count and queue capacity.
// workers and queueSize must be >= 1.
func New(workers, queueSize int, depth DepthFunc) (*Pool, error) {
	if workers < 1 {
		return nil, fmt.Errorf("asyncpool: workers must be >= 1")
	}
	if queueSize < 1 {
		return nil, fmt.Errorf("asyncpool: queueSize must be >= 1")
	}
	p := &Pool{
		jobs:    make(chan func(), queueSize),
		quit:    make(chan struct{}),
		depth:   depth,
		drained: make(chan struct{}),
	}
	for i := 0; i < workers; i++ {
		p.wg.Add(1)
		go p.worker()
	}
	return p, nil
}

// Submit enqueues fn. It blocks when the queue is full until capacity frees
// or Shutdown unblocks via quit. Returns false if the pool is shut down.
func (p *Pool) Submit(fn func()) bool {
	if fn == nil || !p.beginSubmit() {
		return false
	}
	defer p.submitWG.Done()
	select {
	case <-p.quit:
		return false
	case p.jobs <- fn:
		p.reportDepth()
		return true
	}
}

// TrySubmit enqueues fn without blocking. Returns false if the pool is shut
// down or the queue is full (caller should fail-open / drop).
func (p *Pool) TrySubmit(fn func()) bool {
	if fn == nil || !p.beginSubmit() {
		return false
	}
	defer p.submitWG.Done()
	p.sendMu.Lock()
	defer p.sendMu.Unlock()
	if p.closed.Load() {
		return false
	}
	select {
	case p.jobs <- fn:
		p.reportDepth()
		return true
	default:
		return false
	}
}

// beginSubmit accounts for an in-flight submit under gate so Shutdown's Wait
// cannot complete before Add (avoids WaitGroup Add/Wait data race).
func (p *Pool) beginSubmit() bool {
	p.gate.Lock()
	defer p.gate.Unlock()
	if p.closed.Load() {
		return false
	}
	p.submitWG.Add(1)
	return true
}

// Shutdown stops accepting new work, drains the queue, and waits for workers.
// The context deadline bounds how long to wait for in-flight jobs.
func (p *Pool) Shutdown(ctx context.Context) error {
	p.drainOnce.Do(func() {
		p.gate.Lock()
		p.closed.Store(true)
		close(p.quit) // unblock Submit waiting on a full queue
		p.gate.Unlock()
		go func() {
			p.submitWG.Wait()
			p.sendMu.Lock()
			close(p.jobs)
			p.sendMu.Unlock()
			p.wg.Wait()
			close(p.drained)
		}()
	})
	select {
	case <-p.drained:
		p.reportDepth()
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}

func (p *Pool) worker() {
	defer p.wg.Done()
	for fn := range p.jobs {
		p.reportDepth()
		fn()
	}
}

func (p *Pool) reportDepth() {
	if p.depth == nil {
		return
	}
	p.depth(float64(len(p.jobs)))
}
