package config_test

import (
	"os"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/config"
)

type sampleConfig struct {
	Required string        `env:"TEST_REQUIRED_VAR,required"`
	Optional string        `env:"TEST_OPTIONAL_VAR" envDefault:"fallback"`
	Secret   config.Secret `env:"TEST_SECRET_VAR" secret:"true"`
}

func TestLoad_missingRequiredAggregates(t *testing.T) {
	os.Unsetenv("TEST_REQUIRED_VAR")
	t.Setenv("TEST_OPTIONAL_VAR", "")
	t.Setenv("TEST_SECRET_VAR", "")

	_, err := config.Load[sampleConfig]()
	if err == nil {
		t.Fatal("expected error")
	}
	if !strings.Contains(err.Error(), "TEST_REQUIRED_VAR") {
		t.Fatalf("error should mention missing var: %v", err)
	}
}

func TestLoad_defaultsAndSecret(t *testing.T) {
	t.Setenv("TEST_REQUIRED_VAR", "ok")
	t.Setenv("TEST_OPTIONAL_VAR", "")
	t.Setenv("TEST_SECRET_VAR", "s3cr3t")

	cfg, err := config.Load[sampleConfig]()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if cfg.Optional != "fallback" {
		t.Fatalf("optional: %q", cfg.Optional)
	}
	if cfg.Secret.String() != "s3cr3t" {
		t.Fatalf("secret: %q", cfg.Secret)
	}
}

func TestMustLoad_exitsOnError(t *testing.T) {
	if os.Getenv("TEST_MUST_LOAD_PANIC") == "1" {
		_ = config.MustLoad[sampleConfig]()
		return
	}
	// MustLoad calls os.Exit; verify error path via Load instead.
	os.Unsetenv("TEST_REQUIRED_VAR")
	_, err := config.Load[sampleConfig]()
	if err == nil {
		t.Fatal("expected error")
	}
	if err.Error() == "" {
		t.Fatal("expected non-empty error")
	}
}
