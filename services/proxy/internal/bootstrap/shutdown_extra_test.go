package bootstrap

import (
	"bytes"
	"context"
	"database/sql"
	"errors"
	"log/slog"
	"net/http"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/directive"
	"github.com/Rick1330/ibex-harness/packages/logger"
	ibexmetrics "github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
)

func TestUnit_ShutdownDirectiveCache(t *testing.T) {
	t.Parallel()

	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()

	if err := shutdownDirectiveCache(ctx, shutdownOpts{}); err != nil {
		t.Fatalf("nil resolver: %v", err)
	}
	if err := shutdownDirectiveCache(ctx, shutdownOpts{directiveResolver: directive.NoopResolver{}}); err != nil {
		t.Fatalf("noop resolver: %v", err)
	}

	log := logger.Discard("proxy")
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() {
		if err := client.Close(); err != nil {
			t.Errorf("close redis client: %v", err)
		}
	})
	resolver, err := directive.NewCachedResolver(directive.CachedResolverDeps{
		Client: client, Loader: staticDirectiveLoader{}, Config: directive.Config{CacheTTL: time.Minute}, Log: log,
	})
	if err != nil {
		t.Fatalf("resolver: %v", err)
	}
	if err := shutdownDirectiveCache(ctx, shutdownOpts{directiveResolver: resolver}); err != nil {
		t.Fatalf("cached resolver: %v", err)
	}
}

func TestUnit_StopPubSubSubscribers_Idempotent(t *testing.T) {
	t.Parallel()

	var cancels atomic.Int32
	opts := shutdownOpts{
		stopPubSubOnce: &sync.Once{},
		revCancel:      func() { cancels.Add(1) },
		dirCancel:      func() { cancels.Add(1) },
	}

	stopPubSubSubscribers(opts)
	stopPubSubSubscribers(opts)

	if got := cancels.Load(); got != 2 {
		t.Fatalf("cancels=%d want 2 (each cancel once)", got)
	}
}

func TestUnit_ImmediateCleanup_LogsErrors(t *testing.T) {
	t.Parallel()

	var buf bytes.Buffer
	log, err := logger.New(logger.Config{
		Service: "proxy",
		Level:   slog.LevelError,
		Writer:  &buf,
	})
	if err != nil {
		t.Fatal(err)
	}
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	if err := client.Close(); err != nil {
		t.Fatal(err)
	}
	server := &http.Server{
		Addr:              "127.0.0.1:0",
		Handler:           http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {}),
		ReadHeaderTimeout: time.Second,
	}
	opts := shutdownOpts{
		cfg:            config.Config{ShutdownTimeout: time.Second},
		logger:         log,
		server:         server,
		redisClient:    client,
		stopPubSubOnce: &sync.Once{},
	}

	immediateCleanup(opts)

	if !strings.Contains(buf.String(), "immediate cleanup failed") {
		t.Fatalf("expected cleanup error log, got %q", buf.String())
	}
	if !strings.Contains(buf.String(), "redis client close") {
		t.Fatalf("expected redis close operation, got %q", buf.String())
	}
}

func TestUnit_LogImmediateCleanupErr_NilSafe(t *testing.T) {
	t.Parallel()

	logImmediateCleanupErr(nil, "op", errors.New("boom"))
	logImmediateCleanupErr(logger.Discard("proxy"), "op", nil)

	var buf bytes.Buffer
	log, err := logger.New(logger.Config{Service: "proxy", Level: slog.LevelError, Writer: &buf})
	if err != nil {
		t.Fatal(err)
	}

	logImmediateCleanupErr(log, "op", errors.New("boom"))

	if !strings.Contains(buf.String(), "immediate cleanup failed") {
		t.Fatalf("expected log line, got %q", buf.String())
	}
}

func TestUnit_ShutdownHelpers_NilResources(t *testing.T) {
	t.Parallel()

	ctx := context.Background()
	opts := shutdownOpts{}

	if err := shutdownCheckpointPool(ctx, opts); err != nil {
		t.Fatal(err)
	}
	if err := shutdownSessionSweeper(ctx, opts); err != nil {
		t.Fatal(err)
	}
	if err := shutdownTraceWriter(ctx, opts); err != nil {
		t.Fatal(err)
	}
	if err := closeGRPCConns(opts); err != nil {
		t.Fatal(err)
	}
	if err := closeRedisClient(opts); err != nil {
		t.Fatal(err)
	}
	if err := closePgDB(opts); err != nil {
		t.Fatal(err)
	}
}

func TestUnit_StopRevocationOnFailure(t *testing.T) {
	t.Parallel()

	var canceled atomic.Bool

	stopRevocationOnFailure(nil, nil)
	stopRevocationOnFailure(nil, func() { canceled.Store(true) })

	if !canceled.Load() {
		t.Fatal("expected cancel invoked")
	}
}

func TestUnit_SetupSessionHotPath_NilRedis(t *testing.T) {
	t.Parallel()

	cfg := config.Config{CheckpointWorkers: 1, CheckpointQueue: 1}
	cfg.ApplyDefaults()

	parts, err := setupSessionHotPath(nil, cfg, nil)
	if err != nil {
		t.Fatal(err)
	}
	if parts.pool == nil {
		t.Fatal("expected checkpoint pool")
	}
	t.Cleanup(func() {
		if err := parts.pool.Shutdown(context.Background()); err != nil {
			t.Errorf("pool shutdown: %v", err)
		}
	})

	if parts.cache != nil {
		t.Fatal("expected nil cache without redis")
	}
	if parts.turnBuffer != nil {
		t.Fatal("expected nil turn buffer without redis")
	}
}

func TestUnit_NewExtractionTurnBuffer(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })

	buf, err := newExtractionTurnBuffer(client, config.Config{ExtractionTurnsTTL: time.Minute})
	if err != nil || buf == nil {
		t.Fatalf("buf=%v err=%v", buf, err)
	}
	buf2, err := newExtractionTurnBuffer(client, config.Config{SessionIdleTimeout: 2 * time.Minute})
	if err != nil || buf2 == nil {
		t.Fatalf("fallback buf=%v err=%v", buf2, err)
	}
	nilBuf, err := newExtractionTurnBuffer(nil, config.Config{})
	if err != nil || nilBuf != nil {
		t.Fatalf("nil redis: buf=%v err=%v", nilBuf, err)
	}
}

func TestUnit_NewSessionCache_WithRedis(t *testing.T) {
	t.Parallel()

	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() {
		if err := client.Close(); err != nil {
			t.Errorf("redis close: %v", err)
		}
	})
	cfg := config.Config{SessionCacheTTL: time.Minute}

	cache, err := newSessionCache(client, cfg)

	if err != nil {
		t.Fatal(err)
	}
	if cache == nil {
		t.Fatal("expected cache")
	}
}

func TestUnit_SetupSessionStack_NilDB(t *testing.T) {
	t.Parallel()

	cfg := config.Config{CheckpointWorkers: 1, CheckpointQueue: 1}
	cfg.ApplyDefaults()
	reg := ibexmetrics.NewProxy("proxy-stack-test")

	stack, err := setupSessionStack(sessionStackSetup{
		DB: nil, Redis: nil, Config: cfg, Log: logger.Discard("proxy"), Reg: reg,
		Tracer: telemetry.NoopTracer("ibex-session"),
	})

	if err != nil {
		t.Fatal(err)
	}
	if stack.store != nil {
		t.Fatal("expected nil store")
	}
	if stack.sweeper != nil {
		t.Fatal("expected nil sweeper")
	}
	if stack.pool == nil {
		t.Fatal("expected pool")
	}
	t.Cleanup(func() {
		if err := stack.pool.Shutdown(context.Background()); err != nil {
			t.Errorf("pool shutdown: %v", err)
		}
	})
}

func TestUnit_SetupDirectiveResolver_WithRedis(t *testing.T) {
	t.Parallel()

	db := mustStubPostgres(t)
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() {
		if err := client.Close(); err != nil {
			t.Errorf("redis close: %v", err)
		}
	})
	openDB := func(string) (*sql.DB, error) { return db, nil }

	gotDB, resolver, err := setupDirectiveResolver(directiveResolverSetup{
		Config: config.Config{PostgresDSN: "postgres://example/ibex", DirectiveCacheTTL: time.Minute},
		Redis:  client, Log: logger.Discard("proxy"), Reg: ibexmetrics.NewProxy("dir-test"),
		OpenDB: openDB,
	})

	if err != nil {
		t.Fatal(err)
	}
	if gotDB != db {
		t.Fatal("expected stub db")
	}
	if resolver == nil {
		t.Fatal("expected resolver")
	}
}

func TestUnit_CloseRedisClient_WrapsError(t *testing.T) {
	t.Parallel()

	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	if err := client.Close(); err != nil {
		t.Fatal(err)
	}

	err := closeRedisClient(shutdownOpts{redisClient: client})

	if err == nil {
		t.Fatal("expected wrapped close error")
	}
	if !strings.Contains(err.Error(), "close redis client") {
		t.Fatalf("err=%v", err)
	}
}

func TestUnit_StartRevocationSubscriber_SkippedWithoutCache(t *testing.T) {
	t.Parallel()

	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() {
		if err := client.Close(); err != nil {
			t.Errorf("redis close: %v", err)
		}
	})

	sub, cancel, err := startRevocationSubscriber(
		client, stubTokenValidator{}, logger.Discard("proxy"), nil,
	)

	if err != nil {
		t.Fatal(err)
	}
	if sub != nil || cancel != nil {
		t.Fatal("expected skip without CacheInvalidator")
	}
}

type stubTokenValidator struct{}

func (stubTokenValidator) Validate(context.Context, string) (*auth.ValidateResult, error) {
	return nil, errors.New("unused")
}

func TestUnit_NewCheckpointPool_WithMetrics(t *testing.T) {
	t.Parallel()

	cfg := config.Config{CheckpointWorkers: 1, CheckpointQueue: 2}
	cfg.ApplyDefaults()
	reg := ibexmetrics.NewProxy("pool-metrics")

	pool, err := newCheckpointPool(cfg, reg)

	if err != nil {
		t.Fatal(err)
	}
	if pool == nil {
		t.Fatal("expected pool")
	}
	t.Cleanup(func() {
		if err := pool.Shutdown(context.Background()); err != nil {
			t.Errorf("pool shutdown: %v", err)
		}
	})
}
