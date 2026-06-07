package telemetry

import (
	"fmt"
	"os"
	"strconv"
	"strings"
)

const defaultSampleRatio = 0.01

// ConfigFromEnv builds Config from standard OTEL_* environment variables.
// serviceName and environment are IBEX fallbacks when OTEL-specific vars are unset.
func ConfigFromEnv(serviceName, environment string) (Config, error) {
	name := strings.TrimSpace(os.Getenv("OTEL_SERVICE_NAME"))
	if name == "" {
		name = strings.TrimSpace(serviceName)
	}
	if name == "" {
		return Config{}, fmt.Errorf("OTEL_SERVICE_NAME or IBEX_SERVICE_NAME is required")
	}

	env := strings.TrimSpace(os.Getenv("OTEL_DEPLOYMENT_ENVIRONMENT"))
	if env == "" {
		env = strings.TrimSpace(environment)
	}
	if env == "" {
		env = "development"
	}

	ratio := defaultSampleRatio
	if v := strings.TrimSpace(os.Getenv("OTEL_SAMPLE_RATIO")); v != "" {
		parsed, err := strconv.ParseFloat(v, 64)
		if err != nil || parsed < 0 || parsed > 1 {
			return Config{}, fmt.Errorf("OTEL_SAMPLE_RATIO must be a float between 0 and 1")
		}
		ratio = parsed
	}

	return Config{
		ServiceName:    name,
		ServiceVersion: envDefault("OTEL_SERVICE_VERSION", "dev"),
		Environment:    env,
		OTLPEndpoint:   strings.TrimSpace(os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT")),
		SampleRatio:    ratio,
	}, nil
}

func envDefault(key, fallback string) string {
	if v := strings.TrimSpace(os.Getenv(key)); v != "" {
		return v
	}
	return fallback
}
