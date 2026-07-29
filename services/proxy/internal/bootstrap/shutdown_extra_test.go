package bootstrap

import (
	"context"
	"errors"
	"net/http"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
)

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

	server := &http.Server{
		Addr:              "127.0.0.1:0",
		Handler:           http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {}),
		ReadHeaderTimeout: time.Second,
	}
	opts := shutdownOpts{
		cfg:            config.Config{ShutdownTimeout: time.Second},
		logger:         logger.Discard("proxy"),
		server:         server,
		stopPubSubOnce: &sync.Once{},
	}
	immediateCleanup(opts)
	// Second pass covers already-closed server Close error logging.
	immediateCleanup(opts)
}

func TestUnit_LogImmediateCleanupErr_NilSafe(t *testing.T) {
	t.Parallel()

	logImmediateCleanupErr(nil, "op", errors.New("boom"))
	logImmediateCleanupErr(logger.Discard("proxy"), "op", nil)
	logImmediateCleanupErr(logger.Discard("proxy"), "op", errors.New("boom"))
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
	if err := closeGRPCConn(opts); err != nil {
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
	if parts.cache != nil {
		t.Fatal("expected nil cache without redis")
	}
	if parts.pool == nil {
		t.Fatal("expected checkpoint pool")
	}
	t.Cleanup(func() { _ = parts.pool.Shutdown(context.Background()) })
}
