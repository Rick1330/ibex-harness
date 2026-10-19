package config

import (
	"fmt"
	"log/slog"
	"os"
	"strings"
	"time"

	ibexconfig "github.com/Rick1330/ibex-harness/packages/config"
)

const (
	defaultPollInterval     = 2 * time.Second
	defaultBatchSize        = 32
	defaultMaxAttempts      = 8
	defaultRecoverAfter     = 60 * time.Second
	defaultOperationTimeout = 30 * time.Second
	defaultErrorBackoff     = 5 * time.Second
	defaultShutdownTimeout  = 30 * time.Second

	minPollInterval     = 500 * time.Millisecond
	maxPollInterval     = 5 * time.Minute
	minBatchSize        = 1
	maxBatchSize        = 256
	minMaxAttempts      = 1
	maxMaxAttempts      = 100
	minRecoverAfter     = time.Second
	maxRecoverAfter     = time.Hour
	minOperationTimeout = time.Second
	maxOperationTimeout = 5 * time.Minute
	minErrorBackoff     = 500 * time.Millisecond
	maxErrorBackoff     = time.Minute
)

type envConfig struct {
	Environment        string            `env:"IBEX_ENV"`
	ServiceName        string            `env:"IBEX_SERVICE_NAME" envDefault:"relay"`
	LogLevel           string            `env:"IBEX_LOG_LEVEL" envDefault:"INFO"`
	Port               string            `env:"IBEX_PORT" envDefault:"8081"`
	Enabled            string            `env:"IBEX_RELAY_ENABLED" envDefault:"false"`
	PostgresDSN        ibexconfig.Secret `env:"IBEX_RELAY_POSTGRES_DSN" secret:"true"`
	ClickHouseDSN      ibexconfig.Secret `env:"IBEX_RELAY_CLICKHOUSE_DSN" secret:"true"`
	PollInterval       time.Duration     `env:"IBEX_RELAY_POLL_INTERVAL"`
	BatchSize          int               `env:"IBEX_RELAY_BATCH_SIZE"`
	MaxAttempts        int               `env:"IBEX_RELAY_MAX_ATTEMPTS"`
	RecoverAfter       time.Duration     `env:"IBEX_RELAY_RECOVER_AFTER"`
	OperationTimeout   time.Duration     `env:"IBEX_RELAY_OPERATION_TIMEOUT"`
	ErrorBackoff       time.Duration     `env:"IBEX_RELAY_ERROR_BACKOFF"`
	ShutdownTimeoutRaw string            `env:"IBEX_SHUTDOWN_TIMEOUT"`
}

func loadEnvConfig() (envConfig, error) {
	if err := requireExplicitEnvironment(); err != nil {
		return envConfig{}, err
	}
	return ibexconfig.Load[envConfig]()
}

func requireExplicitEnvironment() error {
	raw, ok := os.LookupEnv("IBEX_ENV")
	if !ok || strings.TrimSpace(raw) == "" {
		return fmt.Errorf("IBEX_ENV must be set explicitly to development, staging, or production")
	}
	return nil
}

func buildConfig(envCfg envConfig) (Config, error) {
	level, err := parseLogLevel(envCfg.LogLevel)
	if err != nil {
		return Config{}, err
	}
	enabled, err := parseEnabledFlag(envCfg.Enabled, false)
	if err != nil {
		return Config{}, fmt.Errorf("IBEX_RELAY_ENABLED must be true or false: %w", err)
	}
	shutdownTimeout, err := ibexconfig.ParseShutdownTimeout(envCfg.ShutdownTimeoutRaw, defaultShutdownTimeout)
	if err != nil {
		return Config{}, err
	}
	cfg := Config{
		Environment:      envCfg.Environment,
		ServiceName:      envCfg.ServiceName,
		LogLevel:         level,
		Port:             envCfg.Port,
		Enabled:          enabled,
		PostgresDSN:      envCfg.PostgresDSN,
		ClickHouseDSN:    envCfg.ClickHouseDSN,
		PollInterval:     withDefaultDuration(envCfg.PollInterval, defaultPollInterval),
		BatchSize:        withDefaultInt(envCfg.BatchSize, defaultBatchSize),
		MaxAttempts:      withDefaultInt(envCfg.MaxAttempts, defaultMaxAttempts),
		RecoverAfter:     withDefaultDuration(envCfg.RecoverAfter, defaultRecoverAfter),
		OperationTimeout: withDefaultDuration(envCfg.OperationTimeout, defaultOperationTimeout),
		ErrorBackoff:     withDefaultDuration(envCfg.ErrorBackoff, defaultErrorBackoff),
		ShutdownTimeout:  shutdownTimeout,
	}
	if err := validateConfig(cfg); err != nil {
		return Config{}, err
	}
	return cfg, nil
}

func validateConfig(cfg Config) error {
	if err := validateBounds(cfg); err != nil {
		return err
	}
	return validateEnabledDependencies(cfg)
}

func validateBounds(cfg Config) error {
	if err := validateCountBounds(cfg); err != nil {
		return err
	}
	return validateDurationBounds(cfg)
}

func validateCountBounds(cfg Config) error {
	if cfg.BatchSize < minBatchSize || cfg.BatchSize > maxBatchSize {
		return fmt.Errorf("IBEX_RELAY_BATCH_SIZE must be between %d and %d", minBatchSize, maxBatchSize)
	}
	if cfg.MaxAttempts < minMaxAttempts || cfg.MaxAttempts > maxMaxAttempts {
		return fmt.Errorf("IBEX_RELAY_MAX_ATTEMPTS must be between %d and %d", minMaxAttempts, maxMaxAttempts)
	}
	return nil
}

func validateDurationBounds(cfg Config) error {
	if cfg.PollInterval < minPollInterval || cfg.PollInterval > maxPollInterval {
		return fmt.Errorf("IBEX_RELAY_POLL_INTERVAL must be between %s and %s", minPollInterval, maxPollInterval)
	}
	if cfg.RecoverAfter < minRecoverAfter || cfg.RecoverAfter > maxRecoverAfter {
		return fmt.Errorf("IBEX_RELAY_RECOVER_AFTER must be between %s and %s", minRecoverAfter, maxRecoverAfter)
	}
	if cfg.OperationTimeout < minOperationTimeout || cfg.OperationTimeout > maxOperationTimeout {
		return fmt.Errorf("IBEX_RELAY_OPERATION_TIMEOUT must be between %s and %s", minOperationTimeout, maxOperationTimeout)
	}
	if cfg.ErrorBackoff < minErrorBackoff || cfg.ErrorBackoff > maxErrorBackoff {
		return fmt.Errorf("IBEX_RELAY_ERROR_BACKOFF must be between %s and %s", minErrorBackoff, maxErrorBackoff)
	}
	return nil
}

func validateEnabledDependencies(cfg Config) error {
	if !cfg.Enabled {
		return nil
	}
	if strings.TrimSpace(cfg.PostgresDSN.String()) == "" {
		return fmt.Errorf("IBEX_RELAY_POSTGRES_DSN is required when IBEX_RELAY_ENABLED=true")
	}
	if strings.TrimSpace(cfg.ClickHouseDSN.String()) == "" {
		return fmt.Errorf("IBEX_RELAY_CLICKHOUSE_DSN is required when IBEX_RELAY_ENABLED=true")
	}
	return nil
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

func parseEnabledFlag(raw string, defaultVal bool) (bool, error) {
	v := strings.TrimSpace(strings.ToLower(raw))
	if v == "" {
		return defaultVal, nil
	}
	switch v {
	case "1", "true", "yes", "on":
		return true, nil
	case "0", "false", "no", "off":
		return false, nil
	default:
		return false, fmt.Errorf("must be true or false")
	}
}

func withDefaultDuration(v, def time.Duration) time.Duration {
	if v == 0 {
		return def
	}
	return v
}

func withDefaultInt(v, def int) int {
	if v == 0 {
		return def
	}
	return v
}
