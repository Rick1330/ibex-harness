package config

import (
	"fmt"
	"log/slog"
	"net"
	"os"
	"strings"

	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/google/uuid"
)

func Load() (Config, error) {
	cfg := baseConfigFromEnv()
	cfg.ApplyDefaults()

	level, err := parseLogLevel(getEnv("IBEX_LOG_LEVEL", "INFO"))
	if err != nil {
		return Config{}, err
	}
	cfg.LogLevel = level

	if err := loadOptionalOverrides(&cfg); err != nil {
		return Config{}, err
	}
	telemetryCfg, err := telemetry.ConfigFromEnv(cfg.ServiceName, cfg.Environment)
	if err != nil {
		return Config{}, err
	}
	cfg.Telemetry = telemetryCfg
	if err := cfg.Validate(); err != nil {
		return Config{}, err
	}
	return cfg, nil
}

func baseConfigFromEnv() Config {
	return Config{
		Environment:         getEnv("IBEX_ENV", defaultEnvironment),
		ServiceName:         getEnv("IBEX_SERVICE_NAME", defaultServiceName),
		Port:                getEnv("IBEX_PORT", defaultPort),
		RedisURL:            strings.TrimSpace(os.Getenv("REDIS_URL")),
		AuthGRPCAddr:        getEnv("IBEX_AUTH_GRPC_ADDR", defaultAuthGRPCAddr),
		AuthValidateTimeout: defaultAuthValidateTimeout,
		MaxRequestBodyBytes: defaultMaxRequestBodyBytes,
		RequestIDHeader:     getEnv("IBEX_REQUEST_ID_HEADER", defaultRequestIDHeader),
		TraceIDHeader:       getEnv("IBEX_TRACE_ID_HEADER", defaultTraceIDHeader),
		ErrorDocsBase:       strings.TrimSpace(os.Getenv("IBEX_ERROR_DOCS_BASE")),
		RateLimit: RateLimitConfig{
			DefaultRPM:   defaultRateLimitRPM,
			OrgOverrides: map[uuid.UUID]int{},
		},
	}
}

func ListenAddress(port string) string {
	return net.JoinHostPort("", port)
}

func getEnv(key, fallback string) string {
	value := strings.TrimSpace(os.Getenv(key))
	if value == "" {
		return fallback
	}
	return value
}

func parseLogLevel(value string) (slog.Level, error) {
	switch strings.ToUpper(strings.TrimSpace(value)) {
	case "DEBUG":
		return slog.LevelDebug, nil
	case "INFO":
		return slog.LevelInfo, nil
	case "WARN", "WARNING":
		return slog.LevelWarn, nil
	case "ERROR":
		return slog.LevelError, nil
	default:
		return 0, fmt.Errorf("IBEX_LOG_LEVEL must be DEBUG, INFO, WARN, or ERROR")
	}
}
