package bootstrap

import (
	"context"
	"errors"
	"net/http"
	"os"
	"sync/atomic"
	"syscall"
	"testing"
	"time"

	"github.com/ClickHouse/clickhouse-go/v2/lib/driver"
	"github.com/DATA-DOG/go-sqlmock"
	"github.com/Rick1330/ibex-harness/packages/evidenceoutbox"
	"github.com/Rick1330/ibex-harness/packages/evidenceoutbox/clickhousesink"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/services/relay/internal/config"
	"github.com/google/uuid"
)

type fakeCHRow struct{}

func (fakeCHRow) Scan(...any) error    { return nil }
func (fakeCHRow) ScanStruct(any) error { return nil }
func (fakeCHRow) Err() error           { return nil }

type fakeCHConn struct{}

func (fakeCHConn) QueryRow(context.Context, string, ...any) driver.Row { return fakeCHRow{} }
func (fakeCHConn) Exec(context.Context, string, ...any) error          { return nil }
func (fakeCHConn) Ping(context.Context) error                          { return nil }
func (fakeCHConn) Close() error                                        { return nil }

type noopFence struct{}

func (noopFence) CheckFence(context.Context, uuid.UUID, evidenceoutbox.TombstoneFence) error {
	return nil
}

func newTestSink(t *testing.T) *clickhousesink.Sink {
	t.Helper()
	sink, err := clickhousesink.New(fakeCHConn{}, noopFence{})
	if err != nil {
		t.Fatal(err)
	}
	return sink
}

// baseShutdownOpts builds a shutdownOpts with a diskless DB and a signal
// channel; callers set cancelLoop and the drain timeout they need.
func baseShutdownOpts(t *testing.T, timeout time.Duration, loopDone chan struct{}) (shutdownOpts, chan os.Signal) {
	t.Helper()
	db, _, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	signalCh := make(chan os.Signal, 1)
	var draining atomic.Bool
	opts := shutdownOpts{
		cfg:        config.Config{ShutdownTimeout: timeout},
		log:        logger.Discard("relay-test"),
		server:     &http.Server{Addr: "127.0.0.1:0", Handler: http.NotFoundHandler()},
		draining:   &draining,
		cancelLoop: func() {},
		loopDone:   loopDone,
		rt:         &runtime{db: db, sink: newTestSink(t)},
		signalCh:   signalCh,
	}
	return opts, signalCh
}

func TestRunWithShutdown_GracefulDrainStopsAndCloses(t *testing.T) {
	loopDone := make(chan struct{})
	close(loopDone)
	opts, signalCh := baseShutdownOpts(t, 5*time.Second, loopDone)
	canceled := make(chan struct{})
	opts.cancelLoop = func() { close(canceled) }
	go func() {
		time.Sleep(50 * time.Millisecond)
		signalCh <- syscall.SIGTERM
	}()

	code := runWithShutdown(opts)
	if code != 0 {
		t.Fatalf("exit code: %d", code)
	}
	if !opts.draining.Load() {
		t.Fatal("draining flag must be set")
	}
	select {
	case <-canceled:
	default:
		t.Fatal("loop must be canceled")
	}
}

func TestRunWithShutdown_DrainTimeoutExitsNonZero(t *testing.T) {
	loopDone := make(chan struct{})
	opts, signalCh := baseShutdownOpts(t, 50*time.Millisecond, loopDone)
	go func() {
		time.Sleep(20 * time.Millisecond)
		signalCh <- syscall.SIGTERM
	}()

	if code := runWithShutdown(opts); code != 1 {
		t.Fatalf("drain timeout must exit non-zero, got %d", code)
	}
}

func TestCloseRuntime_ClosesDBAndSink(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	mock.ExpectClose()
	rt := &runtime{db: db, sink: newTestSink(t)}
	if err := closeRuntime(rt); err != nil {
		t.Fatalf("closeRuntime: %v", err)
	}
	if err := db.PingContext(context.Background()); err == nil {
		t.Fatal("db must be closed after closeRuntime")
	}
	if err := closeRuntime(nil); err != nil {
		t.Fatalf("nil runtime: %v", err)
	}
}

func TestImmediateRelayCleanup_CancelsLoopAndCloses(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	mock.ExpectClose()
	var canceled atomic.Bool
	opts := shutdownOpts{
		log:        logger.Discard("relay-test"),
		cancelLoop: func() { canceled.Store(true) },
		rt:         &runtime{db: db, sink: newTestSink(t)},
	}
	immediateRelayCleanup(opts)
	if !canceled.Load() {
		t.Fatal("loop must be canceled")
	}
	if err := db.PingContext(context.Background()); err == nil {
		t.Fatal("db must be closed after immediate cleanup")
	}
}

func TestAwaitRelayShutdown_ServerErrorReturnsOne(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	mock.ExpectClose()
	opts := shutdownOpts{
		log:        logger.Discard("relay-test"),
		cancelLoop: func() {},
		rt:         &runtime{db: db, sink: newTestSink(t)},
	}
	errCh := make(chan error, 1)
	errCh <- errors.New("bind failed")
	if code := awaitRelayShutdown(opts, errCh, make(chan error, 1)); code != 1 {
		t.Fatalf("server error must exit 1, got %d", code)
	}
}

func TestAwaitRelayShutdown_DrainFailureReturnsOne(t *testing.T) {
	opts := shutdownOpts{log: logger.Discard("relay-test")}
	shutdownErrCh := make(chan error, 1)
	shutdownErrCh <- errors.New("drain timed out")
	if code := awaitRelayShutdown(opts, make(chan error, 1), shutdownErrCh); code != 1 {
		t.Fatalf("drain failure must exit 1, got %d", code)
	}
}
