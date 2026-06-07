package config

import (
	"fmt"
	"net"
	"strconv"
	"strings"

	"github.com/google/uuid"
)

func (c Config) Validate() error {
	if err := c.validateEnvironment(); err != nil {
		return err
	}
	if err := c.validateHTTPHeaders(); err != nil {
		return err
	}
	return c.validateRateLimit()
}

func (c Config) validateEnvironment() error {
	if err := c.validateEnvName(); err != nil {
		return err
	}
	if err := c.validatePort(); err != nil {
		return err
	}
	if err := c.validateAuthConfig(); err != nil {
		return err
	}
	return c.validateBodyLimit()
}

func (c Config) validateEnvName() error {
	switch c.Environment {
	case "development", "staging", "production":
		return nil
	default:
		return fmt.Errorf("IBEX_ENV must be one of development, staging, production")
	}
}

func (c Config) validatePort() error {
	if strings.TrimSpace(c.ServiceName) == "" {
		return fmt.Errorf("IBEX_SERVICE_NAME must not be empty")
	}
	return validateTCPPort(c.Port)
}

func validateTCPPort(port string) error {
	portNum, err := strconv.Atoi(port)
	if err != nil {
		return fmt.Errorf("IBEX_PORT must be a valid TCP port")
	}
	if portNum < 1 {
		return fmt.Errorf("IBEX_PORT must be a valid TCP port")
	}
	if portNum > 65535 {
		return fmt.Errorf("IBEX_PORT must be a valid TCP port")
	}
	return nil
}

func (c Config) validateAuthConfig() error {
	if c.Environment != "development" && strings.TrimSpace(c.AuthGRPCAddr) == "" {
		return fmt.Errorf("IBEX_AUTH_GRPC_ADDR is required outside development")
	}
	if strings.TrimSpace(c.AuthGRPCAddr) == "" {
		return nil
	}
	if _, _, err := net.SplitHostPort(c.AuthGRPCAddr); err != nil {
		return fmt.Errorf("IBEX_AUTH_GRPC_ADDR must be host:port: %w", err)
	}
	if c.AuthValidateTimeout <= 0 {
		return fmt.Errorf("IBEX_AUTH_VALIDATE_TIMEOUT must be positive")
	}
	return nil
}

func (c Config) validateBodyLimit() error {
	if c.MaxRequestBodyBytes < 1 {
		return fmt.Errorf("IBEX_MAX_REQUEST_BODY_BYTES must be positive")
	}
	return nil
}

func (c Config) validateHTTPHeaders() error {
	if strings.TrimSpace(c.RequestIDHeader) == "" {
		return fmt.Errorf("IBEX_REQUEST_ID_HEADER must not be empty")
	}
	if strings.TrimSpace(c.TraceIDHeader) == "" {
		return fmt.Errorf("IBEX_TRACE_ID_HEADER must not be empty")
	}
	return nil
}

func (c Config) validateRateLimit() error {
	if c.RateLimit.DefaultRPM < 1 {
		return fmt.Errorf("IBEX_RATE_LIMIT_DEFAULT_RPM must be positive")
	}
	for orgID, rpm := range c.RateLimit.OrgOverrides {
		if rpm < 1 {
			return fmt.Errorf("IBEX_RATE_LIMIT_ORG_OVERRIDES org %s must have positive RPM", orgID)
		}
	}
	return nil
}

func parseOrgRPMOverrides(raw string) (map[uuid.UUID]int, error) {
	out := make(map[uuid.UUID]int)
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return out, nil
	}
	for _, pair := range strings.Split(raw, ",") {
		pair = strings.TrimSpace(pair)
		if pair == "" {
			continue
		}
		parts := strings.SplitN(pair, "=", 2)
		if len(parts) != 2 {
			return nil, fmt.Errorf("invalid pair %q (expected uuid=rpm)", pair)
		}
		orgID, err := uuid.Parse(strings.TrimSpace(parts[0]))
		if err != nil {
			return nil, fmt.Errorf("invalid org UUID in %q: %w", pair, err)
		}
		rpm, err := strconv.Atoi(strings.TrimSpace(parts[1]))
		if err != nil || rpm < 1 {
			return nil, fmt.Errorf("invalid RPM in %q", pair)
		}
		out[orgID] = rpm
	}
	return out, nil
}
