package directive

import (
	"context"
	"sync"
	"sync/atomic"
)

const (
	defaultWriteWorkers = 4
	defaultWriteQueue   = 64
)

type cacheWriteJob struct {
	key      string
	resolved Resolved
}

// writePool runs cache populate jobs on a fixed worker set.
// trySubmit never blocks the request path: a full queue drops the job.
type writePool struct {
	jobs      chan cacheWriteJob
	wg        sync.WaitGroup
	closed    atomic.Bool
	drained   chan struct{}
	drainOnce sync.Once
	handler   func(cacheWriteJob)
}

func newWritePool(workers, queue int, handler func(cacheWriteJob)) *writePool {
	if workers < 1 {
		workers = defaultWriteWorkers
	}
	if queue < 1 {
		queue = defaultWriteQueue
	}
	p := &writePool{
		jobs:    make(chan cacheWriteJob, queue),
		drained: make(chan struct{}),
		handler: handler,
	}
	for i := 0; i < workers; i++ {
		p.wg.Add(1)
		go p.worker()
	}
	return p
}

// trySubmit enqueues a job without blocking. Returns false if shut down or full.
func (p *writePool) trySubmit(job cacheWriteJob) bool {
	if p == nil || p.closed.Load() {
		return false
	}
	select {
	case p.jobs <- job:
		return true
	default:
		return false
	}
}

// shutdown stops accepts, drains queued jobs, and waits for workers.
func (p *writePool) shutdown(ctx context.Context) error {
	if p == nil {
		return nil
	}
	p.closed.Store(true)
	p.drainOnce.Do(func() {
		go func() {
			close(p.jobs)
			p.wg.Wait()
			close(p.drained)
		}()
	})
	select {
	case <-p.drained:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}

func (p *writePool) worker() {
	defer p.wg.Done()
	for job := range p.jobs {
		if p.handler != nil {
			p.handler(job)
		}
	}
}
