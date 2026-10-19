package bootstrap

import (
	"context"
	"os"
	"syscall"
	"testing"
	"time"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/Rick1330/ibex-harness/packages/evidenceoutbox"
	"github.com/Rick1330/ibex-harness/packages/logger"
	ibexmetrics "github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/services/relay/internal/config"
)

func TestRun_GateOffReturnsZero(t *testing.T) {
	t.Setenv("IBEX_ENV", "development")
	t.Setenv("IBEX_RELAY_ENABLED", "false")
	if code := Run([]string{"relay"}); code != 0 {
		t.Fatalf("Run with gate off must return 0, got %d", code)
	}
}

func TestRunBootstrap_DisabledExitsCleanly(t *testing.T) {
	t.Setenv("IBEX_ENV", "development")
	t.Setenv("IBEX_RELAY_ENABLED", "false")
	if code := runBootstrap(nil, nil); code != 0 {
		t.Fatalf("disabled gate must exit 0, got %d", code)
	}
}

func TestRunBootstrap_FailsClosed(t *testing.T) {
	enabledDSNs := map[string]string{
		"IBEX_RELAY_ENABLED":        "true",
		"IBEX_RELAY_POSTGRES_DSN":   "postgres://relay:pw@127.0.0.1:1/ibex?sslmode=disable",
		"IBEX_RELAY_CLICKHOUSE_DSN": "clickhouse://ibex:ibex@127.0.0.1:1/ibex",
	}
	cases := []struct {
		name string
		env  map[string]string
	}{
		{"enabled without DSNs", map[string]string{"IBEX_ENV": "development", "IBEX_RELAY_ENABLED": "true"}},
		{"unreachable dependencies", mergeEnv(map[string]string{"IBEX_ENV": "development", "IBEX_RELAY_OPERATION_TIMEOUT": "1s"}, enabledDSNs)},
		{"missing environment", map[string]string{"IBEX_ENV": ""}},
		{"unknown environment", map[string]string{"IBEX_ENV": "prod"}},
		{"invalid telemetry config", mergeEnv(map[string]string{"IBEX_ENV": "development", "OTEL_SAMPLE_RATIO": "not-a-ratio"}, enabledDSNs)},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			for key, value := range tc.env {
				t.Setenv(key, value)
			}
			if code := runBootstrap(nil, nil); code != 1 {
				t.Fatalf("expected fail closed, got %d", code)
			}
		})
	}
}

func mergeEnv(base, extra map[string]string) map[string]string {
	merged := make(map[string]string, len(base)+len(extra))
	for key, value := range base {
		merged[key] = value
	}
	for key, value := range extra {
		merged[key] = value
	}
	return merged
}

func TestInitRelayTelemetry_EmptyServiceNameFailsClosed(t *testing.T) {
	t.Setenv("OTEL_SERVICE_NAME", "")
	_, err := initRelayTelemetry(context.Background(), config.Config{ServiceName: ""}, logger.Discard("relay-test"))
	if err == nil {
		t.Fatal("empty service name must fail telemetry config")
	}
}

// noopDeliverer satisfies both relay deliverer interfaces without touching a
// sink; the loop only needs it to be non-nil for the lifecycle test.
type noopDeliverer struct{}

func (noopDeliverer) Deliver(context.Context, evidenceoutbox.OutboxRow) error { return nil }

func (noopDeliverer) DeliverWithTombstoneFence(context.Context, evidenceoutbox.OutboxRow, evidenceoutbox.TombstoneFence) error {
	return nil
}

func TestServeRelay_StartsLoopAndShutsDownCleanly(t *testing.T) {
	db, _, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	relay, err := evidenceoutbox.NewRelay(db, noopDeliverer{}, evidenceoutbox.RelayConfig{BatchSize: 1, MaxAttempts: 1})
	if err != nil {
		t.Fatal(err)
	}
	rt := &runtime{db: db, sink: newTestSink(t), relay: relay}
	cfg := config.Config{
		ServiceName:      "relay-test",
		Port:             "0",
		PollInterval:     time.Hour,
		BatchSize:        1,
		MaxAttempts:      1,
		RecoverAfter:     time.Second,
		OperationTimeout: time.Second,
		ErrorBackoff:     10 * time.Millisecond,
		ShutdownTimeout:  5 * time.Second,
	}
	signalCh := make(chan os.Signal, 1)
	go func() {
		time.Sleep(50 * time.Millisecond)
		signalCh <- syscall.SIGTERM
	}()

	if code := serveRelay(cfg, logger.Discard("relay-test"), ibexmetrics.NewRelay("relay-test"), rt, signalCh); code != 0 {
		t.Fatalf("serveRelay exit code: got %d want 0", code)
	}
}
