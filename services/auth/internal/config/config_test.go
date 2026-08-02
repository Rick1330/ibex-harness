package config

import (
	"log/slog"
	"testing"
	"time"
)

func validAuthConfig() Config {
	return Config{
		Environment:      "development",
		ServiceName:      "auth",
		Port:             "8081",
		GRPCPort:         "9091",
		PostgresDSN:      "postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable",
		ValidateTokenRPM: 6000,
		ShutdownTimeout:  30 * time.Second,
	}
}

func TestValidate_rejectsInvalidConfig(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name   string
		mutate func(*Config)
	}{
		{
			name:   "invalid port",
			mutate: func(c *Config) { c.Port = "70000" },
		},
		{
			name: "invalid environment",
			mutate: func(c *Config) {
				c.Environment = "prod"
			},
		},
		{
			name:   "missing postgres dsn",
			mutate: func(c *Config) { c.PostgresDSN = "" },
		},
		{
			name:   "empty service name",
			mutate: func(c *Config) { c.ServiceName = "" },
		},
		{
			name:   "invalid validate token rpm",
			mutate: func(c *Config) { c.ValidateTokenRPM = 0 },
		},
	}

	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			cfg := validAuthConfig()
			tc.mutate(&cfg)
			if err := cfg.Validate(); err == nil {
				t.Fatalf("expected validation error for %s", tc.name)
			}
		})
	}
}

func TestLoadRejectsNonPositiveValidateTokenRPM(t *testing.T) {
	t.Setenv("POSTGRES_DSN", "postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable")
	t.Setenv("IBEX_AUTH_VALIDATE_RPM", "0")
	if _, err := Load(); err == nil {
		t.Fatal("expected error for IBEX_AUTH_VALIDATE_RPM=0")
	}
}

func TestLoadRejectsNonPositiveShutdownTimeout(t *testing.T) {
	t.Setenv("POSTGRES_DSN", "postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable")
	t.Setenv("IBEX_SHUTDOWN_TIMEOUT", "0s")
	if _, err := Load(); err == nil {
		t.Fatal("expected error for zero shutdown timeout")
	}
}

func TestLoadFromEnvHappyPath(t *testing.T) {
	t.Setenv("IBEX_ENV", "development")
	t.Setenv("POSTGRES_DSN", "postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable")
	t.Setenv("IBEX_LOG_LEVEL", "DEBUG")
	t.Setenv("IBEX_ARGON2_MEMORY_KIB", "65536")
	t.Setenv("IBEX_ARGON2_TIME", "2")
	t.Setenv("IBEX_ARGON2_PARALLELISM", "1")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if cfg.LogLevel != slog.LevelDebug {
		t.Fatalf("log level: %v", cfg.LogLevel)
	}
	if cfg.Argon2.MemoryKiB != 65536 || cfg.Argon2.Time != 2 {
		t.Fatalf("argon2: %+v", cfg.Argon2)
	}
	if cfg.Telemetry.ServiceName != "auth" {
		t.Fatalf("telemetry: %+v", cfg.Telemetry)
	}
}

func TestLoadRejectsInvalidLogLevel(t *testing.T) {
	t.Setenv("IBEX_ENV", "development")
	t.Setenv("POSTGRES_DSN", "postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable")
	t.Setenv("IBEX_LOG_LEVEL", "TRACE")

	if _, err := Load(); err == nil {
		t.Fatal("expected invalid log level error")
	}
}

func TestValidateAcceptsDefaultShape(t *testing.T) {
	t.Parallel()

	cfg := Config{
		Environment:      "development",
		ServiceName:      "auth",
		Port:             "8081",
		GRPCPort:         "9091",
		PostgresDSN:      "postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable",
		ValidateTokenRPM: 6000,
		ShutdownTimeout:  30 * time.Second,
	}

	if err := cfg.Validate(); err != nil {
		t.Fatalf("expected config to validate: %v", err)
	}
}

func TestListenAddress(t *testing.T) {
	t.Parallel()
	if got := ListenAddress("8081"); got != ":8081" {
		t.Fatalf("got %q", got)
	}
}
