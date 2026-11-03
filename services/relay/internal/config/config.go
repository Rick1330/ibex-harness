// Package config loads and validates the evidence relay daemon environment.
package config

import (
	"log/slog"
	"time"

	ibexconfig "github.com/Rick1330/ibex-harness/packages/config"
)

// Config is the validated runtime configuration for the relay daemon.
type Config struct {
	Environment      string
	ServiceName      string
	LogLevel         slog.Level
	Port             string
	Enabled          bool
	PostgresDSN      ibexconfig.Secret
	ClickHouseDSN    ibexconfig.Secret
	PollInterval     time.Duration
	BatchSize        int
	MaxAttempts      int
	RecoverAfter     time.Duration
	OperationTimeout time.Duration
	ErrorBackoff     time.Duration
	ShutdownTimeout  time.Duration
}

// Load reads, parses, and validates the environment.
func Load() (Config, error) {
	envCfg, err := loadEnvConfig()
	if err != nil {
		return Config{}, err
	}
	return buildConfig(envCfg)
}
