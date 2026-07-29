package config_test

import (
	"io"
	"os"
	"os/exec"
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
	_ = os.Unsetenv("TEST_REQUIRED_VAR")
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

type nestedConfig struct {
	Host   string        `env:"NESTED_HOST" envDefault:"localhost"`
	Secret config.Secret `env:"NESTED_SECRET" secret:"true"`
}

func withDebugLogger(t *testing.T, logFn func(), assertFn func(out string)) {
	t.Helper()
	r, w, err := os.Pipe()
	if err != nil {
		t.Fatal(err)
	}
	old := os.Stderr
	os.Stderr = w
	logFn()
	_ = w.Close()
	os.Stderr = old
	var buf strings.Builder
	if _, copyErr := io.Copy(&buf, r); copyErr != nil {
		t.Fatalf("read stderr: %v", copyErr)
	}
	_ = r.Close()
	assertFn(buf.String())
}

func TestLogDebug_redactsSecretsAndNestedStructs(t *testing.T) {
	type debugCfg struct {
		Visible string        `env:"DBG_VISIBLE"`
		Secret  config.Secret `env:"DBG_SECRET" secret:"true"`
		Nested  nestedConfig
		Ptr     *nestedConfig
	}
	cfg := debugCfg{
		Visible: "shown",
		Secret:  config.Secret("top-secret"),
		Nested:  nestedConfig{Host: "db.internal", Secret: config.Secret("nested-secret")},
		Ptr:     &nestedConfig{Host: "cache.internal", Secret: config.Secret("ptr-secret")},
	}

	withDebugLogger(t, func() { config.LogDebug(cfg) }, func(out string) {
		if !strings.Contains(out, "shown") {
			t.Fatalf("expected visible value in log: %s", out)
		}
		for _, secret := range []string{"top-secret", "nested-secret", "ptr-secret"} {
			if strings.Contains(out, secret) {
				t.Fatalf("secret leaked in log: %s", out)
			}
		}
		if !strings.Contains(out, "[REDACTED]") {
			t.Fatalf("expected redaction marker: %s", out)
		}
	})
}

func TestLogDebug_redactsNonStructValue(t *testing.T) {
	withDebugLogger(t, func() { config.LogDebug("plain-string") }, func(out string) {
		if !strings.Contains(out, "plain-string") {
			t.Fatalf("log: %s", out)
		}
	})
}

func TestLogDebug_typedNilPointer(t *testing.T) {
	withDebugLogger(t, func() { config.LogDebug((*nestedConfig)(nil)) }, func(out string) {
		if out == "" {
			t.Fatal("expected log output for typed nil pointer")
		}
	})
}

func TestLogDebug_nilNestedPointer(t *testing.T) {
	type wrap struct {
		Ptr *nestedConfig
	}
	withDebugLogger(t, func() { config.LogDebug(wrap{Ptr: nil}) }, func(out string) {
		if out == "" {
			t.Fatal("expected log output")
		}
	})
}

func TestLogDebug_usesFieldNameWhenNoEnvTag(t *testing.T) {
	type noTag struct {
		PlainField string
	}
	withDebugLogger(t, func() { config.LogDebug(noTag{PlainField: "visible"}) }, func(out string) {
		if !strings.Contains(out, "PlainField") {
			t.Fatalf("log: %s", out)
		}
	})
}

func TestMustLoad_exitsOnError(t *testing.T) {
	if os.Getenv("TEST_MUST_LOAD_EXIT") == "1" {
		_ = os.Unsetenv("TEST_REQUIRED_VAR")
		_ = config.MustLoad[sampleConfig]()
		return
	}
	cmd := exec.Command(os.Args[0], "-test.run=^TestMustLoad_exitsOnError$", "-test.v")
	cmd.Env = append(os.Environ(), "TEST_MUST_LOAD_EXIT=1", "TEST_REQUIRED_VAR=")
	err := cmd.Run()
	if exitErr, ok := err.(*exec.ExitError); !ok || exitErr.ExitCode() == 0 {
		t.Fatalf("MustLoad should exit non-zero: %v", err)
	}
}
