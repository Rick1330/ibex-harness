package config

import (
	"fmt"
	"log/slog"
	"net"
	"os"
	"strconv"
	"strings"

	"github.com/Rick1330/ibex-harness/packages/crypto"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
)

const (
	defaultEnvironment = "development"
	defaultServiceName = "auth"
	defaultLogLevel    = slog.LevelInfo
	defaultPort        = "8081"
	defaultGRPCPort    = "9091"
)

type Config struct {
	Environment string
	ServiceName string
	LogLevel    slog.Level
	Port        string
	GRPCPort    string
	PostgresDSN string
	Argon2      token.Argon2Params
}

func Load() (Config, error) {
	cfg := Config{
		Environment: getEnv("IBEX_ENV", defaultEnvironment),
		ServiceName: getEnv("IBEX_SERVICE_NAME", defaultServiceName),
		Port:        getEnv("IBEX_PORT", defaultPort),
		GRPCPort:    getEnv("IBEX_GRPC_PORT", defaultGRPCPort),
		PostgresDSN: strings.TrimSpace(os.Getenv("POSTGRES_DSN")),
		Argon2:      crypto.ProductionParams(),
	}

	level, err := parseLogLevel(getEnv("IBEX_LOG_LEVEL", "INFO"))
	if err != nil {
		return Config{}, err
	}
	cfg.LogLevel = level

	if v := os.Getenv("IBEX_ARGON2_MEMORY_KIB"); v != "" {
		n, err := strconv.ParseUint(strings.TrimSpace(v), 10, 32)
		if err != nil {
			return Config{}, fmt.Errorf("IBEX_ARGON2_MEMORY_KIB: %w", err)
		}
		cfg.Argon2.MemoryKiB = uint32(n)
	}
	if v := os.Getenv("IBEX_ARGON2_TIME"); v != "" {
		n, err := strconv.ParseUint(strings.TrimSpace(v), 10, 32)
		if err != nil {
			return Config{}, fmt.Errorf("IBEX_ARGON2_TIME: %w", err)
		}
		cfg.Argon2.Time = uint32(n)
	}
	if v := os.Getenv("IBEX_ARGON2_PARALLELISM"); v != "" {
		n, err := strconv.ParseUint(strings.TrimSpace(v), 10, 8)
		if err != nil {
			return Config{}, fmt.Errorf("IBEX_ARGON2_PARALLELISM: %w", err)
		}
		cfg.Argon2.Parallelism = uint8(n)
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
	for name, port := range map[string]string{"IBEX_PORT": c.Port, "IBEX_GRPC_PORT": c.GRPCPort} {
		portNum, err := strconv.Atoi(port)
		if err != nil || portNum < 1 || portNum > 65535 {
			return fmt.Errorf("%s must be a valid TCP port", name)
		}
	}
	if c.PostgresDSN == "" {
		return fmt.Errorf("POSTGRES_DSN is required for auth token validation")
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
