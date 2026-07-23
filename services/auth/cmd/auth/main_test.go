package main

import (
	"context"
	"database/sql"
	"net"
	"net/http"
	"os"
	"strconv"
	"syscall"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/Rick1330/ibex-harness/services/auth/internal/config"
	"google.golang.org/grpc"
)

func TestRun_InvalidConfigReturns1(t *testing.T) {
	t.Setenv("IBEX_ENV", "not-valid")
	t.Setenv("POSTGRES_DSN", "postgres://user:pass@127.0.0.1:5432/test?sslmode=disable")

	if got := run(nil); got != 1 {
		t.Fatalf("run() = %d, want 1", got)
	}
}

func TestRun_MissingPostgresDSNReturns1(t *testing.T) {
	t.Setenv("IBEX_ENV", "development")
	t.Setenv("POSTGRES_DSN", "")

	if got := run(nil); got != 1 {
		t.Fatalf("run() = %d, want 1", got)
	}
}

func TestRun_GRPCPortAlreadyInUseReturns1(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = ln.Close() }()

	_, portStr, err := net.SplitHostPort(ln.Addr().String())
	if err != nil {
		t.Fatal(err)
	}

	t.Setenv("IBEX_ENV", "development")
	t.Setenv("POSTGRES_DSN", "postgres://ibex:ibex@127.0.0.1:5432/ibex?sslmode=disable")
	t.Setenv("IBEX_GRPC_PORT", portStr)
	t.Setenv("IBEX_PORT", "0")

	if got := run(nil); got != 1 {
		t.Fatalf("run() = %d, want 1", got)
	}
}

func TestRun_InvalidLoggerLevelReturns1(t *testing.T) {
	t.Setenv("IBEX_ENV", "development")
	t.Setenv("POSTGRES_DSN", "postgres://ibex:ibex@127.0.0.1:5432/ibex?sslmode=disable")
	t.Setenv("IBEX_LOG_LEVEL", "not-a-level")

	if got := run(nil); got != 1 {
		t.Fatalf("run() = %d, want 1", got)
	}
}

func TestRunWithShutdown_serverFailureReturns1(t *testing.T) {
	log := logger.Discard("auth")
	providers, err := telemetry.Init(context.Background(), telemetry.Config{ServiceName: "auth"})
	if err != nil {
		t.Fatal(err)
	}

	db, err := sql.Open("postgres", "postgres://127.0.0.1:5432/test?sslmode=disable")
	if err != nil {
		t.Fatal(err)
	}

	// Invalid listen address forces ListenAndServe error.
	badPort, _ := strconv.Atoi("99999")
	httpServer := &http.Server{
		Addr:              net.JoinHostPort("127.0.0.1", strconv.Itoa(badPort)),
		Handler:           http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {}),
		ReadHeaderTimeout: 5 * time.Second,
	}

	grpcLis, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}

	done := make(chan int, 1)
	go func() {
		done <- runWithShutdown(shutdownOpts{
			cfg: config.Config{
				Environment:     "development",
				ShutdownTimeout: 2 * time.Second,
			},
			logger:     log,
			providers:  providers,
			grpcSrv:    grpc.NewServer(), // nosemgrep: go.grpc.security.grpc-server-insecure-connection
			grpcLis:    grpcLis,
			httpServer: httpServer,
			db:         db,
		})
	}()

	select {
	case code := <-done:
		if code != 1 {
			t.Fatalf("runWithShutdown() = %d, want 1", code)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("timed out waiting for server failure")
	}
}

func TestRunWithShutdown_StopsOnSignal(t *testing.T) {
	log := logger.Discard("auth")
	providers, err := telemetry.Init(context.Background(), telemetry.Config{ServiceName: "auth-shutdown-signal"})
	if err != nil {
		t.Fatal(err)
	}

	db, err := sql.Open("postgres", "postgres://127.0.0.1:5432/test?sslmode=disable")
	if err != nil {
		t.Fatal(err)
	}

	grpcLis, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}

	httpLis, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	httpAddr := httpLis.Addr().String()
	_ = httpLis.Close()

	httpServer := &http.Server{
		Addr:              httpAddr,
		Handler:           http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusOK) }),
		ReadHeaderTimeout: 5 * time.Second,
	}

	sigCh := make(chan os.Signal, 1)
	done := make(chan int, 1)
	go func() {
		done <- runWithShutdown(shutdownOpts{
			cfg: config.Config{
				Environment:     "development",
				Port:            "0",
				GRPCPort:        "0",
				ShutdownTimeout: 2 * time.Second,
			},
			logger:     log,
			providers:  providers,
			grpcSrv:    grpc.NewServer(), // nosemgrep: go.grpc.security.grpc-server-insecure-connection
			grpcLis:    grpcLis,
			httpServer: httpServer,
			db:         db,
			signalCh:   sigCh,
		})
	}()

	waitForTCP(t, grpcLis.Addr().String())
	waitForTCP(t, httpAddr)
	sigCh <- syscall.SIGTERM

	select {
	case code := <-done:
		if code != 0 {
			t.Fatalf("runWithShutdown() = %d, want 0", code)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("timed out waiting for shutdown")
	}
}

func TestConfigurePostgresPool(t *testing.T) {
	t.Parallel()

	db, err := sql.Open("postgres", "postgres://127.0.0.1:5432/test?sslmode=disable")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })

	configurePostgresPool(db)
	if db.Stats().MaxOpenConnections != 10 {
		t.Fatalf("max open: %d", db.Stats().MaxOpenConnections)
	}
}

func TestRun_StopsOnSignal(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	_, portStr, err := net.SplitHostPort(ln.Addr().String())
	if err != nil {
		t.Fatal(err)
	}
	_ = ln.Close()

	grpcLis, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	_, grpcPortStr, err := net.SplitHostPort(grpcLis.Addr().String())
	if err != nil {
		t.Fatal(err)
	}
	_ = grpcLis.Close()

	t.Setenv("IBEX_ENV", "development")
	t.Setenv("POSTGRES_DSN", "postgres://ibex:ibex@127.0.0.1:5432/ibex?sslmode=disable")
	t.Setenv("IBEX_PORT", portStr)
	t.Setenv("IBEX_GRPC_PORT", grpcPortStr)

	sigCh := make(chan os.Signal, 1)
	done := make(chan int, 1)
	go func() { done <- runBootstrap(nil, sigCh) }()

	waitForTCP(t, net.JoinHostPort("127.0.0.1", portStr))
	waitForTCP(t, net.JoinHostPort("127.0.0.1", grpcPortStr))
	sigCh <- syscall.SIGTERM

	select {
	case code := <-done:
		if code != 0 {
			t.Fatalf("runBootstrap() = %d, want 0", code)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("timed out waiting for shutdown")
	}
}

func TestRun_InvalidOTELSampleRatioReturns1(t *testing.T) {
	t.Setenv("IBEX_ENV", "development")
	t.Setenv("POSTGRES_DSN", "postgres://ibex:ibex@127.0.0.1:5432/ibex?sslmode=disable")
	t.Setenv("OTEL_SAMPLE_RATIO", "2")

	if got := run(nil); got != 1 {
		t.Fatalf("run() = %d, want 1", got)
	}
}

func waitForTCP(t *testing.T, addr string) {
	t.Helper()
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		conn, err := net.DialTimeout("tcp", addr, 50*time.Millisecond)
		if err == nil {
			_ = conn.Close()
			return
		}
	}
	t.Fatalf("timeout waiting for %s", addr)
}
