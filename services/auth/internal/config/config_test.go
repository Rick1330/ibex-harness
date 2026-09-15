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
			name:   "non_numeric_port",
			mutate: func(c *Config) { c.Port = "abc" },
		},
		{
			name:   "invalid grpc port",
			mutate: func(c *Config) { c.GRPCPort = "0" },
		},
		{
			name:   "negative validate token rpm",
			mutate: func(c *Config) { c.ValidateTokenRPM = -1 },
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

func TestValidate_CredentialsMasterKey(t *testing.T) {
	t.Parallel()
	t.Run("production_requires_key", func(t *testing.T) {
		t.Parallel()
		cfg := validAuthConfig()
		cfg.Environment = "production"
		cfg.CredentialsMasterKey = ""
		if err := cfg.Validate(); err == nil {
			t.Fatal("expected production master key error")
		}
	})
	t.Run("development_allows_empty", func(t *testing.T) {
		t.Parallel()
		cfg := validAuthConfig()
		cfg.CredentialsMasterKey = ""
		if err := cfg.Validate(); err != nil {
			t.Fatalf("unexpected: %v", err)
		}
	})
	t.Run("rejects_invalid_base64", func(t *testing.T) {
		t.Parallel()
		cfg := validAuthConfig()
		cfg.CredentialsMasterKey = "not-a-key"
		if err := cfg.Validate(); err == nil {
			t.Fatal("expected invalid master key error")
		}
	})
	t.Run("accepts_valid_key", func(t *testing.T) {
		t.Parallel()
		cfg := validAuthConfig()
		cfg.CredentialsMasterKey = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
		if err := cfg.Validate(); err != nil {
			t.Fatalf("unexpected: %v", err)
		}
	})
}

func TestValidate_TOTPSessionConfig(t *testing.T) {
	t.Parallel()
	base := validAuthConfig()
	base.TOTPEnabled = true
	base.CredentialsMasterKey = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
	// Non-empty placeholder only — Validate checks presence, not PEM parse.
	base.JWTPrivateKeyPEM = "test-jwt-private-key-configured"
	base.JWTIssuer = "ibex"
	base.JWTAudience = "dash"

	t.Run("ok", func(t *testing.T) {
		t.Parallel()
		cfg := base
		if err := cfg.Validate(); err != nil {
			t.Fatalf("unexpected: %v", err)
		}
	})
	t.Run("missing_master", func(t *testing.T) {
		t.Parallel()
		cfg := base
		cfg.CredentialsMasterKey = ""
		if err := cfg.Validate(); err == nil {
			t.Fatal("expected error")
		}
	})
	t.Run("missing_jwt_pem", func(t *testing.T) {
		t.Parallel()
		cfg := base
		cfg.JWTPrivateKeyPEM = ""
		if err := cfg.Validate(); err == nil {
			t.Fatal("expected error")
		}
	})
	t.Run("missing_issuer", func(t *testing.T) {
		t.Parallel()
		cfg := base
		cfg.JWTIssuer = "  "
		if err := cfg.Validate(); err == nil {
			t.Fatal("expected error")
		}
	})
	t.Run("missing_audience", func(t *testing.T) {
		t.Parallel()
		cfg := base
		cfg.JWTAudience = ""
		if err := cfg.Validate(); err == nil {
			t.Fatal("expected error")
		}
	})
	t.Run("disabled_skips", func(t *testing.T) {
		t.Parallel()
		cfg := validAuthConfig()
		cfg.TOTPEnabled = false
		cfg.JWTPrivateKeyPEM = ""
		if err := cfg.Validate(); err != nil {
			t.Fatalf("unexpected: %v", err)
		}
	})
}

func TestLoad_JWTDurationOverrides(t *testing.T) {
	t.Setenv("IBEX_ENV", "development")
	t.Setenv("POSTGRES_DSN", "postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable")
	t.Setenv("JWT_ACCESS_TOKEN_TTL", "10m")
	t.Setenv("JWT_REFRESH_TOKEN_TTL", "48h")
	t.Setenv("JWT_STEP_UP_TOKEN_TTL", "2m")
	t.Setenv("IBEX_AUTH_TOTP_ENABLED", "false")
	t.Setenv("IBEX_CREDENTIALS_MASTER_KEY_ID", "  ")
	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if cfg.JWTAccessTTL != 10*time.Minute {
		t.Fatalf("access ttl=%v", cfg.JWTAccessTTL)
	}
	if cfg.JWTRefreshTTL != 48*time.Hour {
		t.Fatalf("refresh ttl=%v", cfg.JWTRefreshTTL)
	}
	if cfg.JWTStepUpTTL != 2*time.Minute {
		t.Fatalf("step-up ttl=%v", cfg.JWTStepUpTTL)
	}
	if cfg.CredentialsMasterKeyID != "v1" {
		t.Fatalf("key id default: %q", cfg.CredentialsMasterKeyID)
	}
}

func TestLoad_JWTDurationRejects(t *testing.T) {
	t.Setenv("IBEX_ENV", "development")
	t.Setenv("POSTGRES_DSN", "postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable")
	t.Setenv("JWT_ACCESS_TOKEN_TTL", "10m")
	t.Setenv("JWT_REFRESH_TOKEN_TTL", "48h")
	t.Setenv("JWT_STEP_UP_TOKEN_TTL", "2m")

	t.Setenv("JWT_ACCESS_TOKEN_TTL", "0s")
	if _, err := Load(); err == nil {
		t.Fatal("expected non-positive access ttl error")
	}
	t.Setenv("JWT_ACCESS_TOKEN_TTL", "10m")
	t.Setenv("JWT_REFRESH_TOKEN_TTL", "nope")
	if _, err := Load(); err == nil {
		t.Fatal("expected bad refresh ttl")
	}
	t.Setenv("JWT_REFRESH_TOKEN_TTL", "48h")
	t.Setenv("JWT_STEP_UP_TOKEN_TTL", "-1s")
	if _, err := Load(); err == nil {
		t.Fatal("expected bad step-up ttl")
	}
}

func TestLoad_TOTPEnabledRequiresJWTFields(t *testing.T) {
	t.Setenv("IBEX_ENV", "development")
	t.Setenv("POSTGRES_DSN", "postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable")
	t.Setenv("IBEX_AUTH_TOTP_ENABLED", "true")
	t.Setenv("IBEX_CREDENTIALS_MASTER_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
	t.Setenv("JWT_PRIVATE_KEY_PEM", "")
	t.Setenv("JWT_ISSUER", "ibex")
	t.Setenv("JWT_AUDIENCE", "dash")
	if _, err := Load(); err == nil {
		t.Fatal("expected missing JWT pem when totp enabled")
	}
}

func TestParseLogLevelViaLoad(t *testing.T) {
	t.Setenv("POSTGRES_DSN", "postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable")
	for _, level := range []string{"INFO", "WARN", "WARNING", "ERROR", "debug"} {
		t.Setenv("IBEX_LOG_LEVEL", level)
		if _, err := Load(); err != nil {
			t.Fatalf("level %s: %v", level, err)
		}
	}
}
