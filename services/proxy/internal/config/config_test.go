package config

import (
	"testing"
	"time"

	"github.com/google/uuid"
)

func validProxyConfig() Config {
	cfg := Config{
		Environment:         "development",
		ServiceName:         "proxy",
		Port:                "8080",
		AuthGRPCAddr:        "127.0.0.1:9091",
		AuthValidateTimeout: defaultAuthValidateTimeout,
		MaxRequestBodyBytes: defaultMaxRequestBodyBytes,
		RequestIDHeader:     defaultRequestIDHeader,
		TraceIDHeader:       defaultTraceIDHeader,
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

func TestApplyDefaults(t *testing.T) {
	t.Parallel()
	var cfg Config
	cfg.ApplyDefaults()
	if cfg.ShutdownTimeout != 30*time.Second {
		t.Fatalf("ShutdownTimeout: %s", cfg.ShutdownTimeout)
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
