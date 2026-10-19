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

func TestRunBootstrap_EnabledWithoutDSNsFailsClosed(t *testing.T) {
	t.Setenv("IBEX_ENV", "development")
	t.Setenv("IBEX_RELAY_ENABLED", "true")
	t.Setenv("IBEX_RELAY_POSTGRES_DSN", "")
	t.Setenv("IBEX_RELAY_CLICKHOUSE_DSN", "")
	if code := runBootstrap(nil, nil); code != 1 {
		t.Fatalf("missing DSNs must fail closed, got %d", code)
	}
}

func TestRunBootstrap_UnreachablePostgresFailsClosed(t *testing.T) {
	t.Setenv("IBEX_ENV", "development")
	t.Setenv("IBEX_RELAY_ENABLED", "true")
	t.Setenv("IBEX_RELAY_POSTGRES_DSN", "postgres://relay:pw@127.0.0.1:1/ibex?sslmode=disable")
	t.Setenv("IBEX_RELAY_CLICKHOUSE_DSN", "clickhouse://ibex:ibex@127.0.0.1:1/ibex")
	t.Setenv("IBEX_RELAY_OPERATION_TIMEOUT", "1s")
	if code := runBootstrap(nil, nil); code != 1 {
		t.Fatalf("unreachable postgres must fail closed, got %d", code)
	}
}

func TestRunBootstrap_MissingEnvironmentFailsClosed(t *testing.T) {
	t.Setenv("IBEX_ENV", "")
	if code := runBootstrap(nil, nil); code != 1 {
		t.Fatalf("missing IBEX_ENV must fail closed, got %d", code)
	}
}

func TestRunBootstrap_TelemetryConfigFailsClosed(t *testing.T) {
	t.Setenv("IBEX_ENV", "development")
	t.Setenv("IBEX_RELAY_ENABLED", "true")
	t.Setenv("IBEX_RELAY_POSTGRES_DSN", "postgres://relay:pw@127.0.0.1:1/ibex?sslmode=disable")
	t.Setenv("IBEX_RELAY_CLICKHOUSE_DSN", "clickhouse://ibex:ibex@127.0.0.1:1/ibex")
	t.Setenv("OTEL_SAMPLE_RATIO", "not-a-ratio")
	if code := runBootstrap(nil, nil); code != 1 {
		t.Fatalf("invalid telemetry config must fail closed, got %d", code)
	}
}

func TestInitRelayTelemetry_EmptyServiceNameFailsClosed(t *testing.T) {
	t.Setenv("OTEL_SERVICE_NAME", "")
	_, err := initRelayTelemetry(context.Background(), config.Config{ServiceName: ""}, logger.Discard("relay-test"))
	if err == nil {
		t.Fatal("empty service name must fail telemetry config")
	}
}

func TestRunBootstrap_UnknownEnvironmentFailsClosed(t *testing.T) {
	t.Setenv("IBEX_ENV", "prod")
	if code := runBootstrap(nil, nil); code != 1 {
		t.Fatalf("unknown IBEX_ENV must fail closed, got %d", code)
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
