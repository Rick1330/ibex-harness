package config

import (
	"log/slog"
	"testing"
)

type loadCase struct {
	name    string
	env     map[string]string
	wantErr bool
	check   func(t *testing.T, cfg Config)
}

func loadCases() []loadCase {
	cases := baseLoadCases()
	return append(cases, contextFlagLoadCases()...)
}

func baseLoadCases() []loadCase {
	return []loadCase{
		{
			name: "happy path",
			env: map[string]string{
				"IBEX_ENV": "development", "IBEX_LOG_LEVEL": "WARN",
				"IBEX_RATE_LIMIT_DEFAULT_RPM":   "500",
				"IBEX_RATE_LIMIT_ORG_OVERRIDES": "550e8400-e29b-41d4-a716-446655440000=1000",
				"REDIS_URL":                     "redis://127.0.0.1:6379/0",
			},
			check: checkHappyPathLoad,
		},
		{
			name: "explicit empty context grpc target skips dial default",
			env: map[string]string{
				"IBEX_ENV":                 "development",
				"IBEX_CONTEXT_GRPC_TARGET": "",
			},
			check: checkEmptyContextTargetDefaults,
		},
		{
			name:    "invalid log level",
			env:     map[string]string{"IBEX_LOG_LEVEL": "VERBOSE"},
			wantErr: true,
		},
		{
			name: "invalid org rpm overrides",
			env: map[string]string{
				"IBEX_ENV": "development", "IBEX_RATE_LIMIT_ORG_OVERRIDES": "not-a-uuid=60",
			},
			wantErr: true,
		},
		{
			name:    "zero shutdown timeout",
			env:     map[string]string{"IBEX_SHUTDOWN_TIMEOUT": "0s"},
			wantErr: true,
		},
	}
}

func contextFlagLoadCases() []loadCase {
	return []loadCase{
		{
			name: "context enabled true",
			env: map[string]string{
				"IBEX_ENV":             "development",
				"IBEX_CONTEXT_ENABLED": "true",
			},
			check: func(t *testing.T, cfg Config) {
				t.Helper()
				if !cfg.ContextEnabled {
					t.Fatal("ContextEnabled = false, want true")
				}
			},
		},
		{
			name: "context embed metadata true",
			env: map[string]string{
				"IBEX_ENV":                    "development",
				"IBEX_CONTEXT_EMBED_METADATA": "true",
			},
			check: func(t *testing.T, cfg Config) {
				t.Helper()
				if !cfg.ContextEmbedMetadata {
					t.Fatal("ContextEmbedMetadata = false, want true")
				}
			},
		},
		{
			name:    "invalid context enabled",
			env:     map[string]string{"IBEX_CONTEXT_ENABLED": "maybe"},
			wantErr: true,
		},
		{
			name:    "invalid context embed metadata",
			env:     map[string]string{"IBEX_CONTEXT_EMBED_METADATA": "maybe"},
			wantErr: true,
		},
	}
}

func checkHappyPathLoad(t *testing.T, cfg Config) {
	t.Helper()
	if cfg.LogLevel != slog.LevelWarn {
		t.Fatalf("log level: %v", cfg.LogLevel)
	}
	if cfg.RateLimit.DefaultRPM != 500 || len(cfg.RateLimit.OrgOverrides) != 1 {
		t.Fatalf("rate limit: %+v", cfg.RateLimit)
	}
	if cfg.ContextGRPCTarget != defaultContextGRPCTarget {
		t.Fatalf("ContextGRPCTarget = %q, want default %q", cfg.ContextGRPCTarget, defaultContextGRPCTarget)
	}
}

func checkEmptyContextTargetDefaults(t *testing.T, cfg Config) {
	t.Helper()
	if cfg.ContextGRPCTarget != "" {
		t.Fatalf("ContextGRPCTarget = %q, want empty so dial is skipped", cfg.ContextGRPCTarget)
	}
	if cfg.ContextAssembleTimeout != defaultContextAssembleTimeout {
		t.Fatalf("ContextAssembleTimeout = %s, want %s", cfg.ContextAssembleTimeout, defaultContextAssembleTimeout)
	}
	if cfg.ContextEnabled {
		t.Fatal("ContextEnabled default must be false")
	}
	if cfg.ContextEmbedMetadata {
		t.Fatal("ContextEmbedMetadata default must be false")
	}
}

func runLoadCase(t *testing.T, tc loadCase) {
	t.Helper()
	withProxyEnv(t, tc.env)
	cfg, err := Load()
	if tc.wantErr {
		if err == nil {
			t.Fatal("expected error")
		}
		return
	}
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if tc.check != nil {
		tc.check(t, cfg)
	}
}

func TestLoad(t *testing.T) {
	for _, tc := range loadCases() {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			runLoadCase(t, tc)
		})
	}
}
