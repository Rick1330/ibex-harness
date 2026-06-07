package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"
)

func loadOptionalOverrides(cfg *Config) error {
	if err := loadMaxBodyBytes(cfg); err != nil {
		return err
	}
	if err := loadAuthValidateTimeout(cfg); err != nil {
		return err
	}
	if err := loadDefaultRPMEnv(cfg); err != nil {
		return err
	}
	if err := loadOrgOverridesEnv(cfg); err != nil {
		return err
	}
	return loadShutdownTimeout(cfg)
}

func loadMaxBodyBytes(cfg *Config) error {
	v := strings.TrimSpace(os.Getenv("IBEX_MAX_REQUEST_BODY_BYTES"))
	if v == "" {
		return nil
	}
	n, err := strconv.ParseInt(v, 10, 64)
	if err != nil || n < 1 {
		return fmt.Errorf("IBEX_MAX_REQUEST_BODY_BYTES must be a positive integer")
	}
	cfg.MaxRequestBodyBytes = n
	return nil
}

func loadAuthValidateTimeout(cfg *Config) error {
	v := strings.TrimSpace(os.Getenv("IBEX_AUTH_VALIDATE_TIMEOUT"))
	if v == "" {
		return nil
	}
	d, err := time.ParseDuration(v)
	if err != nil {
		return fmt.Errorf("IBEX_AUTH_VALIDATE_TIMEOUT: %w", err)
	}
	cfg.AuthValidateTimeout = d
	return nil
}

func loadDefaultRPMEnv(cfg *Config) error {
	v := strings.TrimSpace(os.Getenv("IBEX_RATE_LIMIT_DEFAULT_RPM"))
	if v == "" {
		return nil
	}
	n, err := strconv.Atoi(v)
	if err != nil || n < 1 {
		return fmt.Errorf("IBEX_RATE_LIMIT_DEFAULT_RPM must be a positive integer")
	}
	cfg.RateLimit.DefaultRPM = n
	return nil
}

func loadOrgOverridesEnv(cfg *Config) error {
	v := strings.TrimSpace(os.Getenv("IBEX_RATE_LIMIT_ORG_OVERRIDES"))
	if v == "" {
		return nil
	}
	overrides, err := parseOrgRPMOverrides(v)
	if err != nil {
		return fmt.Errorf("IBEX_RATE_LIMIT_ORG_OVERRIDES: %w", err)
	}
	cfg.RateLimit.OrgOverrides = overrides
	return nil
}
