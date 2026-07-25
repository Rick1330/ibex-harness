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
	wg       sync.WaitGroup
	submitWG sync.WaitGroup
	depth    DepthFunc
	closed   atomic.Bool
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
		jobs:  make(chan func(), queueSize),
		depth: depth,
	}
	for i := 0; i < workers; i++ {
		p.wg.Add(1)
		go p.worker()
	}
	return p, nil
}

// Submit enqueues fn. It blocks when the queue is full until capacity frees
// or Shutdown completes in-flight submits. Returns false if the pool is shut down.
func (p *Pool) Submit(fn func()) bool {
	if fn == nil || p.closed.Load() {
		return false
	}
	p.submitWG.Add(1)
	defer p.submitWG.Done()
	if p.closed.Load() {
		return false
	}
	p.jobs <- fn
	p.reportDepth()
	return true
}

// Shutdown stops accepting new work, drains the queue, and waits for workers.
// The context deadline bounds how long to wait for in-flight jobs.
func (p *Pool) Shutdown(ctx context.Context) error {
	if !p.closed.Swap(true) {
		p.submitWG.Wait()
		close(p.jobs)
	}

	done := make(chan struct{})
	go func() {
		p.wg.Wait()
		close(done)
	}()
	select {
	case <-done:
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
