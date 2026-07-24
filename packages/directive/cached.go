package directive

import (
	"context"
	"fmt"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

// CachedResolver resolves directives via Redis with Postgres fallback.
type CachedResolver struct {
	client  redis.UniversalClient
	store   Store
	cfg     Config
	log     *logger.Logger
	metrics Metrics
}

// NewCachedResolver constructs a CachedResolver. metrics may be nil.
func NewCachedResolver(
	client redis.UniversalClient,
	store Store,
	cfg Config,
	log *logger.Logger,
	metrics Metrics,
) (*CachedResolver, error) {
	if client == nil {
		return nil, fmt.Errorf("directive: redis client is required")
	}
	if store == nil {
		return nil, fmt.Errorf("directive: store is required")
	}
	if log == nil {
		return nil, fmt.Errorf("directive: logger is required")
	}
	cfg.ApplyDefaults()
	if metrics == nil {
		metrics = NoopMetrics{}
	}
	return &CachedResolver{
		client:  client,
		store:   store,
		cfg:     cfg,
		log:     log,
		metrics: metrics,
	}, nil
}

// Resolve loads from Redis, falling back to Postgres on miss or Redis error.
func (r *CachedResolver) Resolve(ctx context.Context, orgID, agentID uuid.UUID) (Resolved, error) {
	start := time.Now()
	defer func() {
		r.metrics.ObserveDirectiveResolveSeconds(time.Since(start).Seconds())
	}()

	key := cacheKey(orgID, agentID)
	if resolved, ok := r.getCached(ctx, key); ok {
		r.metrics.IncDirectiveCacheHit()
		return resolved, nil
	}
	r.metrics.IncDirectiveCacheMiss()

	resolved, err := r.store.Load(ctx, orgID, agentID)
	if err != nil {
		r.metrics.IncDirectiveResolveError()
		return Resolved{}, err
	}
	r.populateCache(ctx, key, resolved)
	return resolved, nil
}

// Invalidate deletes the Redis cache entry for the agent.
func (r *CachedResolver) Invalidate(orgID, agentID uuid.UUID) {
	key := cacheKey(orgID, agentID)
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	if err := r.client.Del(ctx, key).Err(); err != nil {
		r.log.WarnCtx(ctx, "directive cache invalidate failed",
			"org_id", orgID.String(), "agent_id", agentID.String(), "error", err)
	}
}

func (r *CachedResolver) getCached(ctx context.Context, key string) (Resolved, bool) {
	raw, err := r.client.Get(ctx, key).Bytes()
	if err == redis.Nil {
		return Resolved{}, false
	}
	if err != nil {
		r.log.WarnCtx(ctx, "directive cache get failed; treating as miss", "error", err)
		return Resolved{}, false
	}
	resolved, err := unmarshalEnvelope(raw)
	if err != nil {
		r.log.WarnCtx(ctx, "directive cache envelope invalid; treating as miss", "error", err)
		_ = r.client.Del(ctx, key).Err()
		return Resolved{}, false
	}
	return resolved, true
}

func (r *CachedResolver) populateCache(ctx context.Context, key string, resolved Resolved) {
	payload, err := marshalEnvelope(resolved)
	if err != nil {
		r.log.WarnCtx(ctx, "directive cache marshal failed", "error", err)
		return
	}
	if err := r.client.Set(ctx, key, payload, r.cfg.CacheTTL).Err(); err != nil {
		r.log.WarnCtx(ctx, "directive cache set failed", "error", err)
	}
}
