package config

import (
	"fmt"
	"net"
	"strconv"
	"strings"

	"github.com/google/uuid"
)

const errMsgInvalidTCPPort = "IBEX_PORT must be a valid TCP port"

func runValidationSteps(steps ...func() error) error {
	for _, step := range steps {
		if err := step(); err != nil {
			return err
		}
	}
	return nil
}

func (c Config) Validate() error {
	return runValidationSteps(
		c.validateEnvironment,
		c.validateHTTPHeaders,
		c.validateRateLimit,
		c.validateLLMConfig,
	)
}

func (c Config) validateLLMConfig() error {
	mode := strings.ToLower(strings.TrimSpace(c.LLMMode))
	switch mode {
	case "mock", "live":
	default:
		return fmt.Errorf("IBEX_LLM_MODE must be mock or live")
	}
	if mode == "live" && strings.TrimSpace(c.OpenAI.APIKey) == "" {
		return fmt.Errorf("OPENAI_API_KEY is required when IBEX_LLM_MODE=live")
	}
	return nil
}

func (c Config) validateEnvironment() error {
	return runValidationSteps(
		c.validateEnvName,
		c.validatePort,
		c.validateAuthConfig,
		c.validateBodyLimit,
	)
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
		return fmt.Errorf("%s", errMsgInvalidTCPPort)
	}
	if portNum < 1 || portNum > 65535 {
		return fmt.Errorf("%s", errMsgInvalidTCPPort)
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
