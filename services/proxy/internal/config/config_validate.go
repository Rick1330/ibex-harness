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
		c.validateTokenizer,
		c.validateSessionSweeper,
		c.validateClickHouse,
		c.validateIdempotency,
	)
}

func (c Config) validateIdempotency() error {
	if c.IdempotencyTTL <= 0 {
		return fmt.Errorf("IBEX_IDEMPOTENCY_TTL must be positive")
	}
	if c.IdempotencyRedisTimeout <= 0 {
		return fmt.Errorf("IBEX_IDEMPOTENCY_REDIS_TIMEOUT must be positive")
	}
	return nil
}

func (c Config) validateClickHouse() error {
	if c.ClickHouseBatchSize < 1 {
		return fmt.Errorf("CLICKHOUSE_INSERT_BATCH_SIZE must be positive")
	}
	if c.ClickHouseFlushMS < 1 {
		return fmt.Errorf("CLICKHOUSE_INSERT_FLUSH_MS must be positive")
	}
	return nil
}

func (c Config) validateSessionSweeper() error {
	if c.SessionIdleTimeout <= 0 {
		return fmt.Errorf("IBEX_SESSION_IDLE_TIMEOUT must be positive")
	}
	if c.SessionSweepInterval <= 0 {
		return fmt.Errorf("IBEX_SESSION_SWEEP_INTERVAL must be positive")
	}
	if c.SessionIdleTimeout < c.SessionSweepInterval {
		return fmt.Errorf("IBEX_SESSION_IDLE_TIMEOUT must be >= IBEX_SESSION_SWEEP_INTERVAL")
	}
	return nil
}

func (c Config) validateLLMConfig() error {
	mode := strings.ToLower(strings.TrimSpace(c.LLMMode))
	if err := validateLLMMode(mode, c.Environment); err != nil {
		return err
	}
	if err := c.validateSelfHostedConfig(); err != nil {
		return err
	}
	return c.validateLiveLLMCredentials(mode)
}

func validateLLMMode(mode, environment string) error {
	switch mode {
	case envLLMModeMock, envLLMModeLive:
	default:
		return fmt.Errorf("IBEX_LLM_MODE must be mock or live")
	}
	if mode == envLLMModeMock && environment == envProduction {
		return fmt.Errorf("IBEX_LLM_MODE=mock is not allowed when IBEX_ENV=production")
	}
	return nil
}

func (c Config) validateLiveLLMCredentials(mode string) error {
	if mode != envLLMModeLive {
		return nil
	}
	if liveCredentialConfigured(c) {
		return nil
	}
	return fmt.Errorf("IBEX_LLM_MODE=live requires OPENAI_API_KEY, ANTHROPIC_API_KEY, and/or IBEX_SELFHOSTED_ENABLED")
}

func liveCredentialConfigured(c Config) bool {
	if strings.TrimSpace(c.OpenAI.APIKey) != "" {
		return true
	}
	if strings.TrimSpace(c.Anthropic.APIKey) != "" {
		return true
	}
	return c.SelfHosted.Enabled
}

func (c Config) validateSelfHostedConfig() error {
	if !c.SelfHosted.Enabled {
		return nil
	}
	if err := ValidateSelfHostedBaseURL(c.SelfHosted.BaseURL); err != nil {
		return err
	}
	if len(c.SelfHosted.Models) == 0 {
		return fmt.Errorf("IBEX_SELFHOSTED_MODELS is required when IBEX_SELFHOSTED_ENABLED=true")
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
	case envDevelopment, envStaging, envProduction:
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
	if c.Environment != envDevelopment && strings.TrimSpace(c.AuthGRPCAddr) == "" {
		return fmt.Errorf("IBEX_AUTH_GRPC_ADDR is required outside development")
	}
	if strings.TrimSpace(c.AuthGRPCAddr) == "" {
		return c.validateContextGRPCConfig()
	}
	if _, _, err := net.SplitHostPort(c.AuthGRPCAddr); err != nil {
		return fmt.Errorf("IBEX_AUTH_GRPC_ADDR must be host:port: %w", err)
	}
	if c.AuthValidateTimeout <= 0 {
		return fmt.Errorf("IBEX_AUTH_VALIDATE_TIMEOUT must be positive")
	}
	if err := c.validateAuthCache(); err != nil {
		return err
	}
	return c.validateContextGRPCConfig()
}

// validateContextGRPCConfig allows an empty target (skip dial until D.5 feature flag).
// When set, the value must be host:port; timeout must be positive after ApplyDefaults.
func (c Config) validateContextGRPCConfig() error {
	if strings.TrimSpace(c.ContextGRPCTarget) == "" {
		return nil
	}
	if _, _, err := net.SplitHostPort(c.ContextGRPCTarget); err != nil {
		return fmt.Errorf("IBEX_CONTEXT_GRPC_TARGET must be host:port: %w", err)
	}
	if c.ContextAssembleTimeout <= 0 {
		return fmt.Errorf("IBEX_CONTEXT_ASSEMBLE_TIMEOUT must be positive")
	}
	return nil
}

func (c Config) validateAuthCache() error {
	if c.AuthCache.LRUCapacity < 1 {
		return fmt.Errorf("IBEX_AUTH_CACHE_LRU_CAPACITY must be positive")
	}
	if c.AuthCache.LRUMaxTTL <= 0 {
		return fmt.Errorf("IBEX_AUTH_CACHE_LRU_MAX_TTL must be positive")
	}
	if c.AuthCache.LRUMaxTTL > maxAuthCacheLRUMaxTTL {
		return fmt.Errorf("IBEX_AUTH_CACHE_LRU_MAX_TTL must be <= %s", maxAuthCacheLRUMaxTTL)
	}
	if c.AuthCache.BloomExpectedItems < 1 {
		return fmt.Errorf("IBEX_AUTH_CACHE_BLOOM_EXPECTED_ITEMS must be positive")
	}
	if c.AuthCache.BloomFPRate <= 0 || c.AuthCache.BloomFPRate >= 1 {
		return fmt.Errorf("IBEX_AUTH_CACHE_BLOOM_FP_RATE must be in (0,1)")
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
		orgID, rpm, err := parseOrgRPMPair(pair)
		if err != nil {
			return nil, err
		}
		out[orgID] = rpm
	}
	return out, nil
}

func parseOrgRPMPair(pair string) (uuid.UUID, int, error) {
	parts := strings.SplitN(pair, "=", 2)
	if len(parts) != 2 {
		return uuid.Nil, 0, fmt.Errorf("invalid pair %q (expected uuid=rpm)", pair)
	}
	orgID, err := uuid.Parse(strings.TrimSpace(parts[0]))
	if err != nil {
		return uuid.Nil, 0, fmt.Errorf("invalid org UUID in %q: %w", pair, err)
	}
	rpm, err := strconv.Atoi(strings.TrimSpace(parts[1]))
	if err != nil || rpm < 1 {
		return uuid.Nil, 0, fmt.Errorf("invalid RPM in %q", pair)
	}
	return orgID, rpm, nil
}
