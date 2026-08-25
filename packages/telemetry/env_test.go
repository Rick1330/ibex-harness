package telemetry_test

import (
	"testing"

	"github.com/Rick1330/ibex-harness/packages/telemetry"
)

func TestConfigFromEnv_defaults(t *testing.T) {
	t.Setenv("OTEL_SERVICE_NAME", "")
	t.Setenv("OTEL_SERVICE_VERSION", "")
	t.Setenv("OTEL_DEPLOYMENT_ENVIRONMENT", "")
	t.Setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
	t.Setenv("OTEL_SAMPLE_RATIO", "")

	cfg, err := telemetry.ConfigFromEnv("proxy", "staging")
	if err != nil {
		t.Fatalf("ConfigFromEnv: %v", err)
	}
	if cfg.ServiceName != "proxy" || cfg.Environment != "staging" {
		t.Fatalf("cfg: %+v", cfg)
	}
	if cfg.SampleRatio != 0.01 {
		t.Fatalf("sample ratio: %f", cfg.SampleRatio)
	}
}

func TestConfigFromEnv_overrides(t *testing.T) {
	t.Setenv("OTEL_SERVICE_NAME", "otel-proxy")
	t.Setenv("OTEL_SERVICE_VERSION", "1.2.3")
	t.Setenv("OTEL_DEPLOYMENT_ENVIRONMENT", "production")
	t.Setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "collector:4317")
	t.Setenv("OTEL_SAMPLE_RATIO", "0.5")

	cfg, err := telemetry.ConfigFromEnv("ignored", "ignored")
	if err != nil {
		t.Fatalf("ConfigFromEnv: %v", err)
	}
	if cfg.ServiceName != "otel-proxy" || cfg.ServiceVersion != "1.2.3" {
		t.Fatalf("service: %+v", cfg)
	}
	if cfg.Environment != "production" || cfg.OTLPEndpoint != "collector:4317" {
		t.Fatalf("env/endpoint: %+v", cfg)
	}
	if cfg.SampleRatio != 0.5 {
		t.Fatalf("ratio: %f", cfg.SampleRatio)
	}
}

func TestConfigFromEnv_stripsOTLPScheme(t *testing.T) {
	t.Setenv("OTEL_SERVICE_NAME", "proxy")
	t.Setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4317")
	cfg, err := telemetry.ConfigFromEnv("proxy", "development")
	if err != nil {
		t.Fatalf("ConfigFromEnv: %v", err)
	}
	if cfg.OTLPEndpoint != "127.0.0.1:4317" {
		t.Fatalf("endpoint: %q", cfg.OTLPEndpoint)
	}
}

func TestConfigFromEnv_missingServiceName(t *testing.T) {
	t.Setenv("OTEL_SERVICE_NAME", "")
	_, err := telemetry.ConfigFromEnv("", "")
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestConfigFromEnv_invalidSampleRatio(t *testing.T) {
	t.Setenv("OTEL_SERVICE_NAME", "proxy")

	tests := []struct {
		name  string
		ratio string
	}{
		{name: "above one", ratio: "2"},
		{name: "not a float", ratio: "not-a-float"},
	}

	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Setenv("OTEL_SAMPLE_RATIO", tc.ratio)
			_, err := telemetry.ConfigFromEnv("proxy", "development")
			if err == nil {
				t.Fatal("expected error")
			}
		})
	}
}
