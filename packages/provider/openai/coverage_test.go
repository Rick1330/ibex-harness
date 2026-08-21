package openai

import (
	"errors"
	"net"
	"net/http"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
)

func TestClient_SupportedModels(t *testing.T) {
	t.Parallel()
	c := New(Config{APIKey: "k", BaseURL: "http://example.com"}, logger.Discard("openai"), telemetry.NoopTracer("openai"), nil)
	models := c.SupportedModels()
	if len(models) != 4 {
		t.Fatalf("models: %v", models)
	}
	if c.Name() != "openai" {
		t.Fatalf("name=%q", c.Name())
	}
}

func TestUnit_Client_SupportedModels_ExtraModels(t *testing.T) {
	t.Parallel()
	c := New(Config{
		APIKey:  "k",
		BaseURL: "http://example.com",
		ExtraModels: []string{
			"openai/gpt-oss-20b:free",
			"gpt-4o",
			" ",
			"  padded-model-id  ",
			"openai/gpt-oss-20b:free",
		},
	}, logger.Discard("openai"), telemetry.NoopTracer("openai"), nil)
	models := c.SupportedModels()
	if len(models) != 6 {
		t.Fatalf("models: %v", models)
	}
	if models[4] != "openai/gpt-oss-20b:free" {
		t.Fatalf("extra model: %v", models)
	}
	if models[5] != "padded-model-id" {
		t.Fatalf("trimmed padded model: %v", models)
	}
}

func TestConfig_ApplyDefaults_nilUsesDefaultRetries(t *testing.T) {
	t.Parallel()
	cfg := Config{}
	cfg.ApplyDefaults()
	if cfg.MaxRetries == nil || *cfg.MaxRetries != defaultMaxRetries {
		t.Fatalf("max retries: %v", cfg.MaxRetries)
	}
}

func TestConfig_ApplyDefaults_explicitZeroRetriesPreserved(t *testing.T) {
	t.Parallel()
	zero := 0
	cfg := Config{MaxRetries: &zero}
	cfg.ApplyDefaults()
	if cfg.MaxRetries == nil || *cfg.MaxRetries != 0 {
		t.Fatalf("max retries: %v", cfg.MaxRetries)
	}
}

func TestConfig_ApplyDefaults_negativeRetriesClampedToZero(t *testing.T) {
	t.Parallel()
	neg := -1
	cfg := Config{MaxRetries: &neg}
	cfg.ApplyDefaults()
	if cfg.MaxRetries == nil || *cfg.MaxRetries != 0 {
		t.Fatalf("max retries: %v", cfg.MaxRetries)
	}
}

func TestStatusClass_allBuckets(t *testing.T) {
	t.Parallel()
	if provider.StatusClass(http.StatusOK) != "2xx" {
		t.Fatal("expected 2xx")
	}
	if provider.StatusClass(http.StatusInternalServerError) != "5xx" {
		t.Fatal("expected 5xx")
	}
	if provider.StatusClass(http.StatusBadRequest) != "4xx" {
		t.Fatal("expected 4xx")
	}
	if provider.StatusClass(100) != "other" {
		t.Fatal("expected other")
	}
}

func TestRetryAfterHeader_httpDate(t *testing.T) {
	t.Parallel()
	future := time.Now().Add(60 * time.Second).UTC().Format(http.TimeFormat)
	if got := RetryAfterHeader(future); got <= 0 {
		t.Fatalf("retry after: %v", got)
	}
}

func TestNew_nilDepsUseDefaults(t *testing.T) {
	t.Parallel()
	c := New(Config{APIKey: "k", BaseURL: "http://example.com"}, logger.Discard("openai"), nil, nil)
	if c == nil || c.inner == nil {
		t.Fatal("expected client")
	}
}

func TestRetryDelay_capsAtMaxBackoff(t *testing.T) {
	t.Parallel()
	const maxRetryBackoff = 30 * time.Second
	got := provider.RetryDelay(time.Second, 20, maxRetryBackoff)
	if got > maxRetryBackoff {
		t.Fatalf("delay %v exceeds max %v", got, maxRetryBackoff)
	}
}

func TestIsRetryableTransport_timeout(t *testing.T) {
	t.Parallel()
	var netErr timeoutNetError
	if provider.IsRetryableTransport(netErr) {
		t.Fatal("timeout must not retry (ambiguous delivery)")
	}
	if !provider.IsRetryableTransport(&net.OpError{Op: "dial", Err: errors.New("refused")}) {
		t.Fatal("dial should retry")
	}
}

type timeoutNetError struct{}

func (timeoutNetError) Error() string   { return "timeout" }
func (timeoutNetError) Timeout() bool   { return true }
func (timeoutNetError) Temporary() bool { return false }
