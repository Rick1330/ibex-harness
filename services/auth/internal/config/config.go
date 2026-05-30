package config

import (
	"fmt"
	"log/slog"
	"net"
	"os"
	"strconv"
	"strings"
)

const (
	defaultEnvironment = "development"
	defaultServiceName = "auth"
	defaultLogLevel    = slog.LevelInfo
	defaultPort        = "8081"
)

type Config struct {
	Environment string
	ServiceName string
	LogLevel    slog.Level
	Port        string
	PostgresDSN string
}

func Load() (Config, error) {
	cfg := Config{
		Environment: getEnv("IBEX_ENV", defaultEnvironment),
		ServiceName: getEnv("IBEX_SERVICE_NAME", defaultServiceName),
		Port:        getEnv("IBEX_PORT", defaultPort),
		PostgresDSN: strings.TrimSpace(os.Getenv("POSTGRES_DSN")),
	}

	level, err := parseLogLevel(getEnv("IBEX_LOG_LEVEL", "INFO"))
	if err != nil {
		return Config{}, err
	}
	cfg.LogLevel = level

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
