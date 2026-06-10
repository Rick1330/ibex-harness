package config

import (
	"testing"
	"time"
)

func TestValidateRejectsInvalidPort(t *testing.T) {
	cfg := Config{
		Environment: "development",
		ServiceName: "auth",
		Port:        "70000",
	}

	if err := cfg.Validate(); err == nil {
		t.Fatal("expected invalid port error")
	}
}

func TestLoadRejectsNonPositiveShutdownTimeout(t *testing.T) {
	t.Setenv("POSTGRES_DSN", "postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable")
	t.Setenv("IBEX_SHUTDOWN_TIMEOUT", "0s")
	if _, err := Load(); err == nil {
		t.Fatal("expected error for zero shutdown timeout")
	}
}

func TestValidateAcceptsDefaultShape(t *testing.T) {
	cfg := Config{
		Environment:     "development",
		ServiceName:     "auth",
		Port:            "8081",
		GRPCPort:        "9091",
		PostgresDSN:     "postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable",
		ShutdownTimeout: 30 * time.Second,
	}

	if err := cfg.Validate(); err != nil {
		t.Fatalf("expected config to validate: %v", err)
	}
}
