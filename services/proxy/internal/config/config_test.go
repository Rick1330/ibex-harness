package config

import (
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
)

func validProxyConfig() Config {
	cfg := Config{
		Environment:            "development",
		ServiceName:            "proxy",
		Port:                   "8080",
		AuthGRPCAddr:           "127.0.0.1:9091",
		AuthValidateTimeout:    defaultAuthValidateTimeout,
		ContextGRPCTarget:      defaultContextGRPCTarget,
		ContextAssembleTimeout: defaultContextAssembleTimeout,
		MaxRequestBodyBytes:    defaultMaxRequestBodyBytes,
		RequestIDHeader:        defaultRequestIDHeader,
		TraceIDHeader:          defaultTraceIDHeader,
	}
	cfg.ApplyDefaults()
	return cfg
}

func TestValidate_rejectsInvalidConfig(t *testing.T) {
	t.Parallel()
	for _, tc := range invalidProxyConfigCases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			cfg := validProxyConfig()
			tc.mutate(&cfg)
			if err := cfg.Validate(); err == nil {
				t.Fatalf("expected validation error for %s", tc.name)
			}
		})
	}
}

func TestValidate_acceptsValidConfig(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name string
		cfg  Config
	}{
		{name: "default shape", cfg: validProxyConfig()},
		{
			name: "zero config with defaults",
			cfg: func() Config {
				var cfg Config
				cfg.ApplyDefaults()
				cfg.Environment = "development"
				cfg.ServiceName = "proxy"
				cfg.Port = "8080"
				return cfg
			}(),
		},
		{
			name: "live anthropic only",
			cfg: func() Config {
				cfg := validProxyConfig()
				cfg.LLMMode = "live"
				cfg.Anthropic.APIKey = "anth-key"
				return cfg
			}(),
		},
		{
			name: "live openai only",
			cfg: func() Config {
				cfg := validProxyConfig()
				cfg.LLMMode = "live"
				cfg.OpenAI.APIKey = "openai-key"
				return cfg
			}(),
		},
	}

	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			if err := tc.cfg.Validate(); err != nil {
				t.Fatalf("expected config to validate: %v", err)
			}
		})
	}
}

func TestValidate_RequiresRedisOutsideDevelopment(t *testing.T) {
	t.Parallel()
	for _, environment := range []string{"staging", "production"} {
		t.Run(environment, func(t *testing.T) {
			cfg := validProxyConfig()
			cfg.Environment = environment
			if err := cfg.Validate(); err == nil || !strings.Contains(err.Error(), "REDIS_URL is required") {
				t.Fatalf("Validate() error=%v, want missing REDIS_URL error", err)
			}

			cfg.RedisURL = "redis://redis.internal:6379/0"
			if environment == "production" {
				cfg.LLMMode = "live"
				cfg.OpenAI.APIKey = "test-key"
			}
			if err := cfg.Validate(); err != nil {
				t.Fatalf("Validate() with shared Redis: %v", err)
			}
		})
	}
}

func TestValidate_RequiresExplicitEnvironmentAfterDefaults(t *testing.T) {
	t.Parallel()
	cfg := validProxyConfig()
	cfg.Environment = ""
	cfg.ApplyDefaults()
	if cfg.Environment != "" {
		t.Fatalf("ApplyDefaults() selected environment %q without an explicit profile", cfg.Environment)
	}
	if err := cfg.Validate(); err == nil || !strings.Contains(err.Error(), "IBEX_ENV must be one of") {
		t.Fatalf("Validate() error=%v, want explicit IBEX_ENV error", err)
	}
}

func TestUnit_Config_ApplyDefaults(t *testing.T) {
	t.Parallel()
	var cfg Config
	cfg.ApplyDefaults()
	assertApplyDefaultsSession(t, cfg)
	assertApplyDefaultsCheckpoint(t, cfg)
	assertApplyDefaultsClickHouse(t, cfg)
	if cfg.MaxFallbackDepth != defaultMaxFallbackDepth {
		t.Fatalf("MaxFallbackDepth=%d", cfg.MaxFallbackDepth)
	}
}

func TestUnit_Config_MaxFallbackDepthClamp(t *testing.T) {
	t.Parallel()
	cfg := Config{MaxFallbackDepth: 0}
	cfg.ApplyDefaults()
	if cfg.MaxFallbackDepth != 1 {
		t.Fatalf("got %d", cfg.MaxFallbackDepth)
	}
	neg := Config{MaxFallbackDepth: -3}
	neg.ApplyDefaults()
	if neg.MaxFallbackDepth != 1 {
		t.Fatalf("neg got %d", neg.MaxFallbackDepth)
	}
	keep := Config{MaxFallbackDepth: 3}
	keep.ApplyDefaults()
	if keep.MaxFallbackDepth != 3 {
		t.Fatalf("keep got %d", keep.MaxFallbackDepth)
	}
}

func assertApplyDefaultsSession(t *testing.T, cfg Config) {
	t.Helper()
	if cfg.ShutdownTimeout != 30*time.Second {
		t.Fatalf("ShutdownTimeout: %s", cfg.ShutdownTimeout)
	}
	if cfg.SessionCacheTTL != defaultSessionCacheTTL {
		t.Fatalf("SessionCacheTTL: %s", cfg.SessionCacheTTL)
	}
	if cfg.SessionGetOrCreateTO != defaultSessionGetOrCreateTO {
		t.Fatalf("SessionGetOrCreateTO: %s", cfg.SessionGetOrCreateTO)
	}
	if cfg.SessionIdleTimeout != defaultSessionIdleTimeout {
		t.Fatalf("SessionIdleTimeout: %s", cfg.SessionIdleTimeout)
	}
	if cfg.SessionSweepInterval != defaultSessionSweepInterval {
		t.Fatalf("SessionSweepInterval: %s", cfg.SessionSweepInterval)
	}
}

func assertApplyDefaultsCheckpoint(t *testing.T, cfg Config) {
	t.Helper()
	if cfg.CheckpointWorkers != defaultCheckpointWorkers {
		t.Fatalf("CheckpointWorkers: %d", cfg.CheckpointWorkers)
	}
	if cfg.CheckpointQueue != defaultCheckpointQueue {
		t.Fatalf("CheckpointQueue: %d", cfg.CheckpointQueue)
	}
}

func assertApplyDefaultsClickHouse(t *testing.T, cfg Config) {
	t.Helper()
	if cfg.ClickHouseBatchSize != 500 {
		t.Fatalf("ClickHouseBatchSize: %d", cfg.ClickHouseBatchSize)
	}
	if cfg.ClickHouseFlushMS != 200 {
		t.Fatalf("ClickHouseFlushMS: %d", cfg.ClickHouseFlushMS)
	}
	if cfg.IdempotencyTTL != defaultIdempotencyTTL {
		t.Fatalf("IdempotencyTTL: %v", cfg.IdempotencyTTL)
	}
	if cfg.IdempotencyRedisTimeout != defaultIdempotencyRedisTO {
		t.Fatalf("IdempotencyRedisTimeout: %v", cfg.IdempotencyRedisTimeout)
	}
}

func TestUnit_Config_ClickHouseZeroDefaultsNegativeRejected(t *testing.T) {
	t.Parallel()
	cfg := Config{}
	cfg.ApplyDefaults()
	assertApplyDefaultsClickHouse(t, cfg)

	neg := validProxyConfig()
	neg.ClickHouseBatchSize = -10
	neg.ApplyDefaults()
	if neg.ClickHouseBatchSize != -10 {
		t.Fatalf("negative batch should survive defaults, got %d", neg.ClickHouseBatchSize)
	}
	if err := neg.Validate(); err == nil {
		t.Fatal("expected validate error for negative batch")
	}

	negFlush := validProxyConfig()
	negFlush.ClickHouseFlushMS = -1
	negFlush.ApplyDefaults()
	if err := negFlush.Validate(); err == nil {
		t.Fatal("expected validate error for negative flush")
	}
}

func TestUnit_Config_NegativeDurationNotDefaulted(t *testing.T) {
	t.Parallel()
	cfg := validProxyConfig()
	cfg.SessionIdleTimeout = -time.Minute
	cfg.SessionSweepInterval = -time.Second
	cfg.ApplyDefaults()
	if cfg.SessionIdleTimeout != -time.Minute {
		t.Fatalf("idle defaulted: %s", cfg.SessionIdleTimeout)
	}
	if cfg.SessionSweepInterval != -time.Second {
		t.Fatalf("interval defaulted: %s", cfg.SessionSweepInterval)
	}
	if err := cfg.Validate(); err == nil {
		t.Fatal("expected validation error for negative durations")
	}
}

func TestUnit_Config_NegativeCacheTTLSanitized(t *testing.T) {
	t.Parallel()
	cfg := validProxyConfig()
	cfg.SessionCacheTTL = -time.Second
	cfg.SessionGetOrCreateTO = -time.Millisecond
	cfg.DirectiveCacheTTL = -time.Minute
	cfg.ApplyDefaults()
	if cfg.SessionCacheTTL != defaultSessionCacheTTL {
		t.Fatalf("SessionCacheTTL: %s", cfg.SessionCacheTTL)
	}
	if cfg.SessionGetOrCreateTO != defaultSessionGetOrCreateTO {
		t.Fatalf("SessionGetOrCreateTO: %s", cfg.SessionGetOrCreateTO)
	}
	if cfg.DirectiveCacheTTL != defaultDirectiveCacheTTL {
		t.Fatalf("DirectiveCacheTTL: %s", cfg.DirectiveCacheTTL)
	}
}

func TestParseOrgRPMOverrides(t *testing.T) {
	t.Parallel()
	orgID := uuid.MustParse("550e8400-e29b-41d4-a716-446655440000")

	tests := []struct {
		name    string
		raw     string
		wantRPM int
		wantErr bool
	}{
		{name: "valid", raw: orgID.String() + "=1000", wantRPM: 1000},
		{name: "invalid uuid", raw: "not-a-uuid=60", wantErr: true},
		{name: "zero rpm", raw: "550e8400-e29b-41d4-a716-446655440000=0", wantErr: true},
	}

	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			got, err := parseOrgRPMOverrides(tc.raw)
			if tc.wantErr {
				if err == nil {
					t.Fatal("expected error")
				}
				return
			}
			if err != nil {
				t.Fatal(err)
			}
			if got[orgID] != tc.wantRPM {
				t.Fatalf("rpm: %d", got[orgID])
			}
		})
	}
}
