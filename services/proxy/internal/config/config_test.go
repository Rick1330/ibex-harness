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
	}

	if err := cfg.Validate(); err != nil {
		t.Fatalf("expected config to validate: %v", err)
	}
}
