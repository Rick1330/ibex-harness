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
	name, err := resolveServiceName(serviceName)
	if err != nil {
		return Config{}, err
	}

	ratio, err := parseSampleRatioFromEnv()
	if err != nil {
		return Config{}, err
	}

	return Config{
		ServiceName:    name,
		ServiceVersion: envDefault("OTEL_SERVICE_VERSION", "dev"),
		Environment:    resolveDeploymentEnvironment(environment),
		OTLPEndpoint:   strings.TrimSpace(os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT")),
		SampleRatio:    ratio,
	}, nil
}

func resolveServiceName(fallback string) (string, error) {
	name := envDefault("OTEL_SERVICE_NAME", strings.TrimSpace(fallback))
	if name == "" {
		return "", fmt.Errorf("OTEL_SERVICE_NAME or IBEX_SERVICE_NAME is required")
	}
	return name, nil
}

func resolveDeploymentEnvironment(fallback string) string {
	env := envDefault("OTEL_DEPLOYMENT_ENVIRONMENT", strings.TrimSpace(fallback))
	if env == "" {
		return "development"
	}
	return env
}

func parseSampleRatioFromEnv() (float64, error) {
	v := strings.TrimSpace(os.Getenv("OTEL_SAMPLE_RATIO"))
	if v == "" {
		return defaultSampleRatio, nil
	}

	parsed, err := strconv.ParseFloat(v, 64)
	if err != nil {
		return 0, fmt.Errorf("OTEL_SAMPLE_RATIO must be a float between 0 and 1")
	}
	if parsed < 0 || parsed > 1 {
		return 0, fmt.Errorf("OTEL_SAMPLE_RATIO must be a float between 0 and 1")
	}
	return parsed, nil
}

func envDefault(key, fallback string) string {
	if v := strings.TrimSpace(os.Getenv(key)); v != "" {
		return v
	}
	return fallback
}
