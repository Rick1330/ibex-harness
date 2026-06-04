package config

import "testing"

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
}
