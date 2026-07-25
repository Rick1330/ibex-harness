package main

import (
	"context"
	"net"
	"net/http"
	"os"
	"strconv"
	"syscall"
	"testing"
	"time"

	ibexch "github.com/Rick1330/ibex-harness/packages/clickhouse"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	"github.com/alicebob/miniredis/v2"
)

func shutdownTestProviders(t *testing.T) *telemetry.Providers {
	t.Helper()
	providers, err := telemetry.Init(context.Background(), telemetry.Config{ServiceName: "proxy"})
	if err != nil {
		t.Fatal(err)
	}
	return providers
}

func runShutdownTest(t *testing.T, opts shutdownOpts, wantCode int, trigger func()) int {
	t.Helper()
	done := make(chan int, 1)
	go func() { done <- runWithShutdown(opts) }()
	if trigger != nil {
		trigger()
	}
	select {
	case code := <-done:
		if code != wantCode {
			t.Fatalf("runWithShutdown() = %d, want %d", code, wantCode)
		}
		return code
	case <-time.After(5 * time.Second):
		t.Fatal("timed out waiting for shutdown")
		return -1
	}
}

type shutdownSignalCase struct {
	name string
	opts func(t *testing.T) (shutdownOpts, func())
}

func shutdownSignalCases(t *testing.T) []shutdownSignalCase {
	t.Helper()
	baseServer := func() *http.Server {
		return &http.Server{
			Addr:              "127.0.0.1:0",
			Handler:           http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusOK) }),
			ReadHeaderTimeout: 5 * time.Second,
		}
	}
	baseCfg := config.Config{Environment: "development", ShutdownTimeout: 2 * time.Second}
	return []shutdownSignalCase{
		{
			name: "stops on signal",
			opts: func(t *testing.T) (shutdownOpts, func()) {
				sigCh := make(chan os.Signal, 1)
				return shutdownOpts{
					cfg: baseCfg, logger: logger.Discard("proxy"),
					providers: shutdownTestProviders(t), server: baseServer(), signalCh: sigCh,
				}, func() { sigCh <- syscall.SIGTERM }
			},
		},
		{
			name: "closes optional clients",
			opts: func(t *testing.T) (shutdownOpts, func()) {
				mr := miniredis.RunT(t)
				redisClient, err := ratelimit.ParseRedisURL("redis://" + mr.Addr() + "/0")
				if err != nil {
					t.Fatal(err)
				}
				sigCh := make(chan os.Signal, 1)
				return shutdownOpts{
					cfg: baseCfg, logger: logger.Discard("proxy"),
					providers: shutdownTestProviders(t), server: baseServer(),
					redisClient: redisClient, signalCh: sigCh,
				}, func() { sigCh <- syscall.SIGTERM }
			},
		},
		{
			name: "drains clickhouse trace writer",
			opts: func(t *testing.T) (shutdownOpts, func()) {
				w := ibexch.NewWriterWithInserter(noopTraceInserter{}, ibexch.Config{
					MaxBatchSize:  10,
					FlushInterval: time.Hour,
				})
				sigCh := make(chan os.Signal, 1)
				return shutdownOpts{
					cfg: baseCfg, logger: logger.Discard("proxy"),
					providers: shutdownTestProviders(t), server: baseServer(),
					traceWriter: w, signalCh: sigCh,
				}, func() { sigCh <- syscall.SIGTERM }
			},
		},
	}
}

type noopTraceInserter struct{}

func (noopTraceInserter) InsertTraces(context.Context, []ibexch.TraceRecord) error { return nil }
func (noopTraceInserter) Close() error                                             { return nil }

func TestRunWithShutdown_serverFailureReturns1(t *testing.T) {
	badPort, _ := strconv.Atoi("99999")
	server := &http.Server{
		Addr:              net.JoinHostPort("127.0.0.1", strconv.Itoa(badPort)),
		Handler:           http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {}),
		ReadHeaderTimeout: 5 * time.Second,
	}
	runShutdownTest(t, shutdownOpts{
		cfg:    config.Config{Environment: "development", ShutdownTimeout: 2 * time.Second},
		logger: logger.Discard("proxy"), providers: shutdownTestProviders(t), server: server,
	}, 1, nil)
}

func TestRunWithShutdown_onSignal(t *testing.T) {
	for _, tc := range shutdownSignalCases(t) {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			opts, trigger := tc.opts(t)
			runShutdownTest(t, opts, 0, trigger)
		})
	}
}
