package config

import (
	"fmt"
	"strings"
	"time"
)

// ParseShutdownTimeout applies IBEX_SHUTDOWN_TIMEOUT when set; otherwise returns defaultVal.
// Returns an error when the env var is set to a non-positive duration.
func ParseShutdownTimeout(raw string, defaultVal time.Duration) (time.Duration, error) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return defaultVal, nil
	}
	d, err := time.ParseDuration(raw)
	if err != nil || d <= 0 {
		return 0, fmt.Errorf("IBEX_SHUTDOWN_TIMEOUT must be positive")
	}
	return d, nil
}
