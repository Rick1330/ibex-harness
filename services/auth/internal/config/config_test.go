package config

import "testing"

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

func TestValidateAcceptsDefaultShape(t *testing.T) {
	cfg := Config{
		Environment: "development",
		ServiceName: "auth",
		Port:        "8081",
		GRPCPort:    "9091",
		PostgresDSN: "postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable",
	}

	if err := cfg.Validate(); err != nil {
		t.Fatalf("expected config to validate: %v", err)
	}
}
