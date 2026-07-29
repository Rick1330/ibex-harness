package sessionsweeper

import (
	"context"
	"fmt"
	"sync"
	"sync/atomic"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/session"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/sessioncache"
)

const (
	defaultBatchLimit    = 500
	defaultTickTimeout   = 15 * time.Second
	defaultIdleTimeout   = 45 * time.Minute
	defaultSweepInterval = time.Minute
)

// Metrics records sweeper outcomes (low-cardinality labels only).
type Metrics interface {
	IncSessionSweeperMarked(status string)
	IncSessionSweeperRun(result string)
}

// Config holds sweeper timing and batch bounds.
type Config struct {
	IdleTimeout time.Duration
	Interval    time.Duration
	BatchLimit  int
}

// Deps wires store, optional cache, logging, and metrics.
type Deps struct {
	Store   session.Store
	Cache   *sessioncache.Cache
	Log     *logger.Logger
	Metrics Metrics
	Now     func() time.Time
}

// Sweeper periodically abandons idle sessions.
type Sweeper struct {
	store      session.Store
	cache      *sessioncache.Cache
	log        *logger.Logger
	metrics    Metrics
	now        func() time.Time
	idle       time.Duration
	interval   time.Duration
	batchLimit int

	cancel  context.CancelFunc
	done    chan struct{}
	wg      sync.WaitGroup
	started atomic.Bool
	busy    atomic.Bool
}

// New validates deps and returns a stopped sweeper.
func New(cfg Config, deps Deps) (*Sweeper, error) {
	if deps.Store == nil {
		return nil, fmt.Errorf("sessionsweeper: store is required")
	}
	idle, interval, err := normalizeTiming(cfg)
	if err != nil {
		return nil, err
	}
	now := deps.Now
	if now == nil {
		now = time.Now
	}
	return &Sweeper{
		store: deps.Store, cache: deps.Cache, log: deps.Log, metrics: deps.Metrics,
		now: now, idle: idle, interval: interval, batchLimit: normalizeBatch(cfg.BatchLimit),
		done: make(chan struct{}),
	}, nil
}

func normalizeTiming(cfg Config) (time.Duration, time.Duration, error) {
	idle := cfg.IdleTimeout
	if idle <= 0 {
		idle = defaultIdleTimeout
	}
	interval := cfg.Interval
	if interval <= 0 {
		interval = defaultSweepInterval
	}
	if idle < interval {
		return 0, 0, fmt.Errorf("sessionsweeper: idle timeout must be >= sweep interval")
	}
	return idle, interval, nil
}

func normalizeBatch(limit int) int {
	if limit < 1 {
		return defaultBatchLimit
	}
	return limit
}

// Start launches the background ticker. Calling Start twice is a no-op.
func (s *Sweeper) Start() {
	if !s.started.CompareAndSwap(false, true) {
		return
	}
	ctx, cancel := context.WithCancel(context.Background())
	s.cancel = cancel
	s.wg.Add(1)
	go s.loop(ctx)
}

// Stop cancels the ticker and waits for the loop (and in-flight tick) to exit.
// Returns ctx.Err() if the caller's deadline or cancellation wins first.
func (s *Sweeper) Stop(ctx context.Context) error {
	if s.cancel == nil {
		return nil
	}
	s.cancel()
	select {
	case <-s.done:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}

func (s *Sweeper) loop(ctx context.Context) {
	defer s.wg.Done()
	defer close(s.done)

	ticker := time.NewTicker(s.interval)
	defer ticker.Stop()

	s.runTick()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			s.runTick()
		}
	}
}

func (s *Sweeper) runTick() {
	if !s.busy.CompareAndSwap(false, true) {
		return
	}
	defer s.busy.Store(false)

	tickCtx, cancel := context.WithTimeout(context.Background(), defaultTickTimeout)
	defer cancel()
	s.tick(tickCtx)
}

func (s *Sweeper) tick(ctx context.Context) {
	res, err := s.store.AbandonIdle(ctx, session.AbandonIdleParams{
		IdleBefore: s.now().UTC().Add(-s.idle), Limit: s.batchLimit,
	})
	if err != nil {
		s.recordRun("error")
		s.warn("session sweeper tick failed", "error", err.Error())
		return
	}
	s.handleResult(ctx, res)
}

func (s *Sweeper) handleResult(ctx context.Context, res session.AbandonIdleResult) {
	if res.SkippedLock {
		s.recordRun("skipped_lock")
		return
	}
	if res.Count() == 0 {
		s.recordRun("noop")
		return
	}
	s.invalidateAbandoned(ctx, res.Abandoned)
	s.recordMarked(res.Count())
	s.recordRun("ok")
}

func (s *Sweeper) invalidateAbandoned(ctx context.Context, rows []session.AbandonedSession) {
	if s.cache == nil {
		return
	}
	for _, row := range rows {
		ext := externalIDValue(row.ExternalID)
		if ext == "" {
			continue
		}
		s.cache.Invalidate(ctx, sessioncache.LookupKey{
			OrgID: row.OrgID, AgentID: row.AgentID, ExternalID: ext,
		})
	}
}

func externalIDValue(ext *string) string {
	if ext == nil {
		return ""
	}
	return *ext
}

func (s *Sweeper) recordMarked(n int) {
	if s.metrics == nil {
		return
	}
	for i := 0; i < n; i++ {
		s.metrics.IncSessionSweeperMarked("abandoned")
	}
}

func (s *Sweeper) recordRun(result string) {
	if s.metrics == nil {
		return
	}
	s.metrics.IncSessionSweeperRun(result)
}

func (s *Sweeper) warn(msg string, kv ...any) {
	if s.log == nil {
		return
	}
	s.log.WarnCtx(context.Background(), msg, kv...)
}
