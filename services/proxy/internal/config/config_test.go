package config

import (
	"testing"

	"github.com/google/uuid"
)

func TestValidateRejectsInvalidEnvironment(t *testing.T) {
	cfg := Config{
		Environment: "prod",
		ServiceName: "proxy",
		Port:        "8080",
	}

	if err := cfg.Validate(); err == nil {
		t.Fatal("expected invalid environment error")
	}
}

func TestValidateAcceptsDefaultShape(t *testing.T) {
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

	if err := cfg.Validate(); err != nil {
		t.Fatalf("expected config to validate: %v", err)
	}
}

func TestApplyDefaultsZeroConfigValidates(t *testing.T) {
	var cfg Config
	cfg.ApplyDefaults()
	cfg.Environment = "development"
	cfg.ServiceName = "proxy"
	cfg.Port = "8080"
	if err := cfg.Validate(); err != nil {
		t.Fatalf("expected zero config with defaults to validate: %v", err)
	}
	if cfg.RequestIDHeader != defaultRequestIDHeader {
		t.Fatalf("RequestIDHeader: %s", cfg.RequestIDHeader)
	}
	if cfg.MaxRequestBodyBytes != defaultMaxRequestBodyBytes {
		t.Fatalf("MaxRequestBodyBytes: %d", cfg.MaxRequestBodyBytes)
	}
	if cfg.RateLimit.DefaultRPM != defaultRateLimitRPM {
		t.Fatalf("RateLimit.DefaultRPM: %d", cfg.RateLimit.DefaultRPM)
	}
}

func TestParseOrgRPMOverrides(t *testing.T) {
	orgID := uuid.MustParse("550e8400-e29b-41d4-a716-446655440000")
	got, err := parseOrgRPMOverrides(orgID.String() + "=1000")
	if err != nil {
		t.Fatal(err)
	}
	if got[orgID] != 1000 {
		t.Fatalf("rpm: %d", got[orgID])
	}
}

func TestParseOrgRPMOverrides_invalid(t *testing.T) {
	if _, err := parseOrgRPMOverrides("not-a-uuid=60"); err == nil {
		t.Fatal("expected error")
	}
	if _, err := parseOrgRPMOverrides("550e8400-e29b-41d4-a716-446655440000=0"); err == nil {
		t.Fatal("expected error for zero rpm")
	}
}
