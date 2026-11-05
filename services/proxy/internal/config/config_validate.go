package config

import (
	"context"
	"fmt"
	"net"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/Rick1330/ibex-harness/packages/policysnapshot"
	"github.com/google/uuid"
)

const errMsgInvalidTCPPort = "IBEX_PORT must be a valid TCP port"

// contextServiceTokenPattern is the ADR-0096 caller-token wire contract, mirrored
// from the context server (services/context/app/grpc_auth.py). It is enforced
// here as well because gRPC-Go rejects metadata values outside ASCII key rules:
// a token carrying a newline, a non-ASCII rune, or more than 512 characters
// makes every RPC fail as Internal, which the startup probe can only classify as
// inconclusive. That would leave the proxy running with a token the context
// server can never accept.
var contextServiceTokenPattern = regexp.MustCompile(`^[A-Za-z0-9_-]{32,512}$`)

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
		c.validatePolicySnapshot,
	)
}

// validatePolicySnapshot validates the optional GAP-002 policy snapshot key
// set. Empty keys disable the stage; when set, keys must parse.
func (c Config) validatePolicySnapshot() error {
	if c.PolicyMinEpoch < 0 {
		return fmt.Errorf("IBEX_PROXY_POLICY_MIN_EPOCH must be non-negative")
	}
	raw := strings.TrimSpace(c.PolicyPublicKeysJSON)
	if raw == "" {
		return nil
	}
	if _, err := policysnapshot.ParseKeySetJSON(raw); err != nil {
		return fmt.Errorf("IBEX_PROXY_POLICY_PUBLIC_KEYS: %w", err)
	}
	return nil
}

func (c Config) validateIdempotency() error {
	if c.IdempotencyTTL <= 0 {
		return fmt.Errorf("IBEX_IDEMPOTENCY_TTL must be positive")
	}
	if c.IdempotencyRedisTimeout <= 0 {
		return fmt.Errorf("IBEX_IDEMPOTENCY_REDIS_TIMEOUT must be positive")
	}
	if c.BudgetReservationLease < minBudgetReservationLease || c.BudgetReservationLease > maxBudgetReservationLease {
		return fmt.Errorf("IBEX_BUDGET_RESERVATION_LEASE must be between 1m and 24h")
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

// contextCallerInputs groups the three ADR-0096 caller-auth inputs the
// context-client validators need: the environment gates TLS, the host bounds
// where the cleartext token may travel, and the token itself.
type contextCallerInputs struct {
	environment string
	host        string
	token       string
}

// validateContextGRPCConfig allows an empty target (skip dial until D.5 feature flag).
// When set, the value must be host:port; timeout must be positive after ApplyDefaults.
// When context assembly is enabled it additionally enforces the ADR-0096 caller
// constraints: the environment must be TLS-free (development/test), the target
// must be loopback, and the service token must be present.
func (c Config) validateContextGRPCConfig() error {
	target := strings.TrimSpace(c.ContextGRPCTarget)
	if target == "" {
		return nil
	}
	if target != c.ContextGRPCTarget {
		return fmt.Errorf(
			"IBEX_CONTEXT_GRPC_TARGET must not have leading or trailing whitespace: validation trims it but the dial would use the raw value",
		)
	}
	host, _, err := net.SplitHostPort(target)
	if err != nil {
		return fmt.Errorf("IBEX_CONTEXT_GRPC_TARGET must be host:port: %w", err)
	}
	if c.ContextAssembleTimeout <= 0 {
		return fmt.Errorf("IBEX_CONTEXT_ASSEMBLE_TIMEOUT must be positive")
	}
	return c.validateEnabledContextCaller(contextCallerInputs{
		environment: c.Environment,
		host:        host,
		token:       c.ContextGRPCServiceToken,
	})
}

// validateEnabledContextCaller enforces the caller-auth preconditions that only
// matter when Assemble can actually run. A disabled client never carries the
// token, so its target and token stay unconstrained beyond host:port.
func (c Config) validateEnabledContextCaller(caller contextCallerInputs) error {
	if !c.ContextEnabled {
		return nil
	}
	if err := validateContextEnvironment(caller.environment); err != nil {
		return err
	}
	if err := validateContextTargetLoopback(caller.host); err != nil {
		return err
	}
	return validateContextServiceToken(caller.token)
}

// validateContextServiceToken requires a token the context server will accept.
// The error names the variable and the allowed shape and never echoes the value,
// because the value is a secret.
func validateContextServiceToken(token string) error {
	if strings.TrimSpace(token) == "" {
		return fmt.Errorf("IBEX_CONTEXT_GRPC_SERVICE_TOKEN is required when IBEX_CONTEXT_ENABLED=true and IBEX_CONTEXT_GRPC_TARGET is set")
	}
	if !contextServiceTokenPattern.MatchString(token) {
		return fmt.Errorf(
			"IBEX_CONTEXT_GRPC_SERVICE_TOKEN must be 32-512 characters from [A-Za-z0-9_-] (ADR-0096); the context server enforces the same shape, and gRPC-Go rejects any other value as metadata so the token could never authenticate",
		)
	}
	return nil
}

// validateContextEnvironment refuses to enable context outside development.
// The context server serves plaintext only; authTransportCredentials would dial
// TLS for any other environment and every Assemble would fail silently (fail-open
// to directive-only), which looks healthy while context is dead. "test" is not a
// deployable IBEX_ENV profile and is TLS-classified by the transport helper, so it
// is rejected here too.
func validateContextEnvironment(environment string) error {
	if environment == envDevelopment {
		return nil
	}
	return fmt.Errorf(
		"IBEX_CONTEXT_ENABLED=true is not supported when IBEX_ENV=%s: the context service does not serve TLS, so this proxy would dial it with TLS credentials and every Assemble would fail; enable context only in development",
		environment,
	)
}

// contextTargetResolveTimeout bounds DNS resolution during config validation so
// startup cannot hang on a slow resolver.
const contextTargetResolveTimeout = 2 * time.Second

// validateContextTargetLoopback requires the context client target to resolve
// exclusively to loopback addresses. The service token travels in cleartext
// gRPC metadata, so a non-loopback endpoint would expose it (ADR-0096).
func validateContextTargetLoopback(host string) error {
	host = strings.TrimSpace(host)
	if host == "" {
		return fmt.Errorf("IBEX_CONTEXT_GRPC_TARGET must include a host")
	}
	ips, err := resolveTargetIPs(host)
	if err != nil {
		return fmt.Errorf("IBEX_CONTEXT_GRPC_TARGET host %q must resolve to a loopback address: %w", host, err)
	}
	for _, ip := range ips {
		if ip.IsUnspecified() || !ip.IsLoopback() {
			return fmt.Errorf(
				"IBEX_CONTEXT_GRPC_TARGET host %q resolves to %s; the context service token must not be sent to a non-loopback endpoint",
				host, ip,
			)
		}
	}
	return nil
}

func resolveTargetIPs(host string) ([]net.IP, error) {
	if ip := net.ParseIP(host); ip != nil {
		return []net.IP{ip}, nil
	}
	ctx, cancel := context.WithTimeout(context.Background(), contextTargetResolveTimeout)
	defer cancel()
	addrs, err := net.DefaultResolver.LookupHost(ctx, host)
	if err != nil {
		return nil, fmt.Errorf("resolve: %w", err)
	}
	if len(addrs) == 0 {
		return nil, fmt.Errorf("no addresses resolved")
	}
	return parseResolvedIPs(addrs)
}

func parseResolvedIPs(addrs []string) ([]net.IP, error) {
	ips := make([]net.IP, 0, len(addrs))
	for _, addr := range addrs {
		ip := net.ParseIP(addr)
		if ip == nil {
			return nil, fmt.Errorf("unparseable resolved address %q", addr)
		}
		ips = append(ips, ip)
	}
	return ips, nil
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
	if c.Environment != envDevelopment && strings.TrimSpace(c.RedisURL) == "" {
		return fmt.Errorf("REDIS_URL is required outside development; shared rate limiting must not be disabled")
	}
	if c.RateLimit.DefaultRPM < 1 {
		return fmt.Errorf("IBEX_RATE_LIMIT_DEFAULT_RPM must be positive")
	}
	if c.RateLimit.GlobalRPM < 1 {
		return fmt.Errorf("IBEX_RATE_LIMIT_GLOBAL_RPM must be positive")
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
