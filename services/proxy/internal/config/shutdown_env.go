package config

import (
	"fmt"
	"os"
	"strings"
	"time"
)

func loadShutdownTimeout(cfg *Config) error {
	v := strings.TrimSpace(os.Getenv("IBEX_SHUTDOWN_TIMEOUT"))
	if v == "" {
		return nil
	}
	d, err := time.ParseDuration(v)
	if err != nil {
		return fmt.Errorf("IBEX_SHUTDOWN_TIMEOUT: %w", err)
	}
	if d <= 0 {
		return fmt.Errorf("IBEX_SHUTDOWN_TIMEOUT must be positive")
	}
	cfg.ShutdownTimeout = d
	return nil
}
