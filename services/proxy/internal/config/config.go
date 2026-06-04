package config

import (
	"fmt"
	"log/slog"
	"net"
	"os"
	"strconv"
	"strings"
	"time"
)

const (
	defaultEnvironment         = "development"
	defaultServiceName         = "proxy"
	defaultLogLevel            = slog.LevelInfo
	defaultPort                = "8080"
	defaultAuthGRPCAddr        = "127.0.0.1:9091"
	defaultAuthValidateTimeout = 50 * time.Millisecond
	defaultRequestIDHeader     = "X-Request-ID"
	defaultTraceIDHeader       = "X-Trace-ID"
	defaultMaxRequestBodyBytes = 1 * 1024 * 1024
)

type Config struct {
	Environment         string
	ServiceName         string
	LogLevel            slog.Level
	Port                string
	RedisURL            string
	AuthGRPCAddr        string
	AuthValidateTimeout time.Duration
	MaxRequestBodyBytes int64
	RequestIDHeader     string
	TraceIDHeader       string
	ErrorDocsBase       string
}

// ApplyDefaults fills zero-valued fields so httptest and partial Config literals behave like Load().
func (c *Config) ApplyDefaults() {
	if strings.TrimSpace(c.Environment) == "" {
		c.Environment = defaultEnvironment
	}
	if strings.TrimSpace(c.ServiceName) == "" {
		c.ServiceName = defaultServiceName
	}
	if c.LogLevel == 0 {
		c.LogLevel = defaultLogLevel
	}
	if strings.TrimSpace(c.Port) == "" {
		c.Port = defaultPort
	}
	if strings.TrimSpace(c.AuthGRPCAddr) == "" {
		c.AuthGRPCAddr = defaultAuthGRPCAddr
	}
	if c.AuthValidateTimeout <= 0 {
		c.AuthValidateTimeout = defaultAuthValidateTimeout
	}
	if c.MaxRequestBodyBytes < 1 {
		c.MaxRequestBodyBytes = defaultMaxRequestBodyBytes
	}
	if strings.TrimSpace(c.RequestIDHeader) == "" {
		c.RequestIDHeader = defaultRequestIDHeader
	}
	if strings.TrimSpace(c.TraceIDHeader) == "" {
		c.TraceIDHeader = defaultTraceIDHeader
	}
}

func Load() (Config, error) {
	cfg := Config{
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
	}

	level, err := parseLogLevel(getEnv("IBEX_LOG_LEVEL", "INFO"))
	if err != nil {
		return Config{}, err
	}
	cfg.LogLevel = level

	if v := strings.TrimSpace(os.Getenv("IBEX_MAX_REQUEST_BODY_BYTES")); v != "" {
		n, err := strconv.ParseInt(v, 10, 64)
		if err != nil || n < 1 {
			return Config{}, fmt.Errorf("IBEX_MAX_REQUEST_BODY_BYTES must be a positive integer")
		}
		cfg.MaxRequestBodyBytes = n
	}

	if v := strings.TrimSpace(os.Getenv("IBEX_AUTH_VALIDATE_TIMEOUT")); v != "" {
		d, err := time.ParseDuration(v)
		if err != nil {
			return Config{}, fmt.Errorf("IBEX_AUTH_VALIDATE_TIMEOUT: %w", err)
		}
		cfg.AuthValidateTimeout = d
	}

	if err := cfg.Validate(); err != nil {
		return Config{}, err
	}
	return cfg, nil
}

func (c Config) Validate() error {
	switch c.Environment {
	case "development", "staging", "production":
	default:
		return fmt.Errorf("IBEX_ENV must be one of development, staging, production")
	}
	if strings.TrimSpace(c.ServiceName) == "" {
		return fmt.Errorf("IBEX_SERVICE_NAME must not be empty")
	}
	portNum, err := strconv.Atoi(c.Port)
	if err != nil || portNum < 1 || portNum > 65535 {
		return fmt.Errorf("IBEX_PORT must be a valid TCP port")
	}
	if c.Environment != "development" && strings.TrimSpace(c.AuthGRPCAddr) == "" {
		return fmt.Errorf("IBEX_AUTH_GRPC_ADDR is required outside development")
	}
	if strings.TrimSpace(c.AuthGRPCAddr) != "" {
		if _, _, err := net.SplitHostPort(c.AuthGRPCAddr); err != nil {
			return fmt.Errorf("IBEX_AUTH_GRPC_ADDR must be host:port: %w", err)
		}
	}
	if c.AuthValidateTimeout <= 0 {
		return fmt.Errorf("IBEX_AUTH_VALIDATE_TIMEOUT must be positive")
	}
	if c.MaxRequestBodyBytes < 1 {
		return fmt.Errorf("IBEX_MAX_REQUEST_BODY_BYTES must be positive")
	}
	if strings.TrimSpace(c.RequestIDHeader) == "" {
		return fmt.Errorf("IBEX_REQUEST_ID_HEADER must not be empty")
	}
	if strings.TrimSpace(c.TraceIDHeader) == "" {
		return fmt.Errorf("IBEX_TRACE_ID_HEADER must not be empty")
	}
	return nil
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
