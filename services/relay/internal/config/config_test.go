package config

import (
	"log/slog"
	"os"
	"strings"
	"testing"
	"time"
)

func setBaseEnv(t *testing.T) {
	t.Helper()
	t.Setenv("IBEX_ENV", "development")
	t.Setenv("IBEX_RELAY_ENABLED", "false")
}

func TestLoad_DisabledByDefault(t *testing.T) {
	setBaseEnv(t)
	cfg, err := Load()
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if cfg.Enabled {
		t.Fatal("relay must be disabled by default")
	}
	if cfg.Port != "8081" {
		t.Fatalf("port: got %q want 8081", cfg.Port)
	}
	if cfg.BatchSize != defaultBatchSize || cfg.MaxAttempts != defaultMaxAttempts {
		t.Fatalf("defaults: %+v", cfg)
	}
	if cfg.PollInterval != defaultPollInterval || cfg.RecoverAfter != defaultRecoverAfter {
		t.Fatalf("duration defaults: %+v", cfg)
	}
}

func TestLoad_RequiresExplicitEnvironment(t *testing.T) {
	t.Setenv("IBEX_RELAY_ENABLED", "false")
	t.Setenv("IBEX_ENV", "")
	if _, err := Load(); err == nil || !strings.Contains(err.Error(), "IBEX_ENV") {
		t.Fatalf("want IBEX_ENV error, got %v", err)
	}
}

func TestLoad_RejectsUnknownEnvironment(t *testing.T) {
	t.Setenv("IBEX_RELAY_ENABLED", "false")
	for _, raw := range []string{"prod", "test", "Production"} {
		t.Run(raw, func(t *testing.T) {
			t.Setenv("IBEX_ENV", raw)
			if _, err := Load(); err == nil || !strings.Contains(err.Error(), "IBEX_ENV") {
				t.Fatalf("env %q must be rejected, got %v", raw, err)
			}
		})
	}
}

func TestLoad_EnabledRequiresPostgresDSN(t *testing.T) {
	setBaseEnv(t)
	t.Setenv("IBEX_RELAY_ENABLED", "true")
	t.Setenv("IBEX_RELAY_POSTGRES_DSN", "")
	t.Setenv("IBEX_RELAY_CLICKHOUSE_DSN", "clickhouse://ibex:ibex@ch:9000/ibex")
	if _, err := Load(); err == nil || !strings.Contains(err.Error(), "IBEX_RELAY_POSTGRES_DSN") {
		t.Fatalf("want postgres DSN error, got %v", err)
	}
}

func TestLoad_EnabledRequiresClickHouseDSN(t *testing.T) {
	setBaseEnv(t)
	t.Setenv("IBEX_RELAY_ENABLED", "true")
	t.Setenv("IBEX_RELAY_POSTGRES_DSN", "postgres://relay:pw@db:5432/ibex?sslmode=disable")
	t.Setenv("IBEX_RELAY_CLICKHOUSE_DSN", "")
	if _, err := Load(); err == nil || !strings.Contains(err.Error(), "IBEX_RELAY_CLICKHOUSE_DSN") {
		t.Fatalf("want clickhouse DSN error, got %v", err)
	}
}

func TestLoad_EnabledWithBothDSNs(t *testing.T) {
	setBaseEnv(t)
	t.Setenv("IBEX_RELAY_ENABLED", "true")
	t.Setenv("IBEX_RELAY_POSTGRES_DSN", "postgres://relay:pw@db:5432/ibex?sslmode=disable")
	t.Setenv("IBEX_RELAY_CLICKHOUSE_DSN", "clickhouse://ibex:ibex@ch:9000/ibex")
	cfg, err := Load()
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if !cfg.Enabled {
		t.Fatal("relay must be enabled")
	}
	if cfg.PostgresDSN.String() == "" || cfg.ClickHouseDSN.String() == "" {
		t.Fatalf("enabled config: %+v", cfg)
	}
}

func TestLoad_EnabledFlagVariants(t *testing.T) {
	setBaseEnv(t)
	t.Setenv("IBEX_RELAY_POSTGRES_DSN", "postgres://relay:pw@db:5432/ibex?sslmode=disable")
	t.Setenv("IBEX_RELAY_CLICKHOUSE_DSN", "clickhouse://ibex:ibex@ch:9000/ibex")
	for _, raw := range []string{"1", "true", "TRUE", "yes", "on"} {
		t.Setenv("IBEX_RELAY_ENABLED", raw)
		cfg, err := Load()
		if err != nil {
			t.Fatalf("load %q: %v", raw, err)
		}
		if !cfg.Enabled {
			t.Fatalf("value %q must enable the relay", raw)
		}
	}
	t.Setenv("IBEX_RELAY_ENABLED", "sometimes")
	if _, err := Load(); err == nil || !strings.Contains(err.Error(), "IBEX_RELAY_ENABLED") {
		t.Fatalf("want enabled flag error, got %v", err)
	}
}

func TestLoad_Bounds(t *testing.T) {
	cases := []struct {
		name string
		env  string
		val  string
		want string
	}{
		{"poll_too_small", "IBEX_RELAY_POLL_INTERVAL", "100ms", "IBEX_RELAY_POLL_INTERVAL"},
		{"poll_too_large", "IBEX_RELAY_POLL_INTERVAL", "10m", "IBEX_RELAY_POLL_INTERVAL"},
		{"batch_too_large", "IBEX_RELAY_BATCH_SIZE", "257", "IBEX_RELAY_BATCH_SIZE"},
		{"batch_negative", "IBEX_RELAY_BATCH_SIZE", "-1", "IBEX_RELAY_BATCH_SIZE"},
		{"attempts_zero_is_default_but_negative_fails", "IBEX_RELAY_MAX_ATTEMPTS", "-2", "IBEX_RELAY_MAX_ATTEMPTS"},
		{"attempts_too_large", "IBEX_RELAY_MAX_ATTEMPTS", "101", "IBEX_RELAY_MAX_ATTEMPTS"},
		{"recover_too_small", "IBEX_RELAY_RECOVER_AFTER", "100ms", "IBEX_RELAY_RECOVER_AFTER"},
		{"recover_too_large", "IBEX_RELAY_RECOVER_AFTER", "2h", "IBEX_RELAY_RECOVER_AFTER"},
		{"operation_too_small", "IBEX_RELAY_OPERATION_TIMEOUT", "100ms", "IBEX_RELAY_OPERATION_TIMEOUT"},
		{"operation_too_large", "IBEX_RELAY_OPERATION_TIMEOUT", "10m", "IBEX_RELAY_OPERATION_TIMEOUT"},
		{"backoff_too_small", "IBEX_RELAY_ERROR_BACKOFF", "100ms", "IBEX_RELAY_ERROR_BACKOFF"},
		{"backoff_too_large", "IBEX_RELAY_ERROR_BACKOFF", "2m", "IBEX_RELAY_ERROR_BACKOFF"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			setBaseEnv(t)
			t.Setenv(tc.env, tc.val)
			_, err := Load()
			if err == nil || !strings.Contains(err.Error(), tc.want) {
				t.Fatalf("env %s=%s: want %q error, got %v", tc.env, tc.val, tc.want, err)
			}
		})
	}
}

func TestLoad_BoundaryValuesAccepted(t *testing.T) {
	setBaseEnv(t)
	t.Setenv("IBEX_RELAY_POLL_INTERVAL", minPollInterval.String())
	t.Setenv("IBEX_RELAY_BATCH_SIZE", "256")
	t.Setenv("IBEX_RELAY_MAX_ATTEMPTS", "100")
	t.Setenv("IBEX_RELAY_RECOVER_AFTER", maxRecoverAfter.String())
	t.Setenv("IBEX_RELAY_OPERATION_TIMEOUT", maxOperationTimeout.String())
	t.Setenv("IBEX_RELAY_ERROR_BACKOFF", minErrorBackoff.String())
	cfg, err := Load()
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if cfg.BatchSize != 256 || cfg.MaxAttempts != 100 {
		t.Fatalf("bounds: %+v", cfg)
	}
}

func TestLoad_ShutdownTimeout(t *testing.T) {
	setBaseEnv(t)
	t.Setenv("IBEX_SHUTDOWN_TIMEOUT", "45s")
	cfg, err := Load()
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if cfg.ShutdownTimeout != 45*time.Second {
		t.Fatalf("shutdown timeout: got %s", cfg.ShutdownTimeout)
	}
}

func TestLoad_LogLevelValidation(t *testing.T) {
	setBaseEnv(t)
	t.Setenv("IBEX_LOG_LEVEL", "chatty")
	if _, err := Load(); err == nil || !strings.Contains(err.Error(), "IBEX_LOG_LEVEL") {
		t.Fatalf("want log level error, got %v", err)
	}
}

func TestParseLogLevel(t *testing.T) {
	for raw, want := range map[string]slog.Level{
		"debug":   slog.LevelDebug,
		"INFO":    slog.LevelInfo,
		"Warn":    slog.LevelWarn,
		"warning": slog.LevelWarn,
		" error ": slog.LevelError,
	} {
		got, err := parseLogLevel(raw)
		if err != nil || got != want {
			t.Fatalf("parseLogLevel(%q) = %v, %v; want %v", raw, got, err, want)
		}
	}
	if _, err := parseLogLevel("chatty"); err == nil {
		t.Fatal("invalid level must error")
	}
}

func TestRequireExplicitEnvironment_Unset(t *testing.T) {
	orig, had := os.LookupEnv("IBEX_ENV")
	if err := os.Unsetenv("IBEX_ENV"); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if had {
			_ = os.Setenv("IBEX_ENV", orig)
		}
	})
	if err := requireExplicitEnvironment(); err == nil {
		t.Fatal("unset IBEX_ENV must fail closed")
	}
}

func TestParseEnabledFlag_Invalid(t *testing.T) {
	if _, err := parseEnabledFlag("maybe", false); err == nil {
		t.Fatal("invalid enabled flag must fail")
	}
}

func TestLoad_InvalidEnabledFlag(t *testing.T) {
	setBaseEnv(t)
	t.Setenv("IBEX_RELAY_ENABLED", "maybe")
	if _, err := Load(); err == nil {
		t.Fatal("invalid IBEX_RELAY_ENABLED must fail")
	}
}

func TestParseEnabledFlag_EmptyUsesDefault(t *testing.T) {
	got, err := parseEnabledFlag("", true)
	if err != nil || !got {
		t.Fatalf("empty flag must use default, got value=%v err=%v", got, err)
	}
}

func TestLoad_InvalidShutdownTimeout(t *testing.T) {
	setBaseEnv(t)
	t.Setenv("IBEX_SHUTDOWN_TIMEOUT", "not-a-duration")
	if _, err := Load(); err == nil {
		t.Fatal("invalid IBEX_SHUTDOWN_TIMEOUT must fail")
	}
}
