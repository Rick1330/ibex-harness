package directive

import (
	"context"
	"fmt"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"
)

// InvalidateTimeout bounds a single Redis DEL during Invalidate.
const InvalidateTimeout = 2 * time.Second

// CachedResolverDeps groups construction dependencies (≤4 ctor params).
type CachedResolverDeps struct {
	Client  redis.UniversalClient
	Loader  Loader
	Config  Config
	Log     *logger.Logger
	Metrics Metrics
	Tracer  trace.Tracer
}

// CachedResolver resolves directives via Redis with Postgres fallback.
type CachedResolver struct {
	client  redis.UniversalClient
	loader  Loader
	cfg     Config
	log     *logger.Logger
	metrics Metrics
	tracer  trace.Tracer
}

// NewCachedResolver constructs a CachedResolver. Metrics/Tracer may be nil.
func NewCachedResolver(deps CachedResolverDeps) (*CachedResolver, error) {
	if deps.Client == nil {
		return nil, fmt.Errorf("directive: redis client is required")
	}
	if deps.Loader == nil {
		return nil, fmt.Errorf("directive: loader is required")
	}
	if deps.Log == nil {
		return nil, fmt.Errorf("directive: logger is required")
	}
	deps.Config.ApplyDefaults()
	if deps.Metrics == nil {
		deps.Metrics = NoopMetrics{}
	}
	if deps.Tracer == nil {
		deps.Tracer = otel.Tracer("ibex-directive")
	}
	return &CachedResolver{
		client:  deps.Client,
		loader:  deps.Loader,
		cfg:     deps.Config,
		log:     deps.Log,
		metrics: deps.Metrics,
		tracer:  deps.Tracer,
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

	resolved, err := r.loader.Load(ctx, orgID, agentID)
	if err != nil {
		r.metrics.IncDirectiveResolveError()
		return Resolved{}, err
	}
	// Write-behind: never block the hot path on Redis SET (own 2s budget).
	go r.populateCache(key, resolved)
	return resolved, nil
}

// Invalidate deletes the Redis cache entry for the agent.
func (r *CachedResolver) Invalidate(ctx context.Context, orgID, agentID uuid.UUID) {
	key := cacheKey(orgID, agentID)
	delCtx, cancel := context.WithTimeout(ctx, InvalidateTimeout)
	defer cancel()
	ctx, span := r.tracer.Start(delCtx, "directive.RedisDel",
		trace.WithAttributes(redisSpanAttrs("DEL")...))
	defer span.End()
	if err := r.client.Del(ctx, key).Err(); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, err.Error())
		r.log.WarnCtx(ctx, "directive cache invalidate failed",
			"org_id", orgID.String(), "agent_id", agentID.String(), "error", err)
	}
}

func (r *CachedResolver) getCached(ctx context.Context, key string) (Resolved, bool) {
	ctx, span := r.tracer.Start(ctx, "directive.RedisGet",
		trace.WithAttributes(redisSpanAttrs("GET")...))
	defer span.End()

	raw, err := r.client.Get(ctx, key).Bytes()
	if err == redis.Nil {
		return Resolved{}, false
	}
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, err.Error())
		r.log.WarnCtx(ctx, "directive cache get failed; treating as miss", "error", err)
		return Resolved{}, false
	}
	resolved, err := unmarshalEnvelope(raw)
	if err != nil {
		span.RecordError(err)
		r.log.WarnCtx(ctx, "directive cache envelope invalid; treating as miss", "error", err)
		_ = r.client.Del(ctx, key).Err() //nolint:errcheck // best-effort: stale cache entry expires naturally via TTL
		return Resolved{}, false
	}
	return resolved, true
}

func (r *CachedResolver) populateCache(key string, resolved Resolved) {
	payload, err := marshalEnvelope(resolved)
	if err != nil {
		r.log.WarnCtx(context.Background(), "directive cache marshal failed", "error", err)
		return
	}
	// Detached from the request: slow SET must not extend ResolveTimeout.
	ctx, cancel := context.WithTimeout(context.Background(), InvalidateTimeout)
	defer cancel()
	ctx, span := r.tracer.Start(ctx, "directive.RedisSet",
		trace.WithAttributes(redisSpanAttrs("SET")...))
	defer span.End()
	if err := r.client.Set(ctx, key, payload, r.cfg.CacheTTL).Err(); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, err.Error())
		r.log.WarnCtx(ctx, "directive cache set failed", "error", err)
	}
}
