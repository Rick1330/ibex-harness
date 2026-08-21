package config

import (
	"log/slog"
	"strings"
	"time"

	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/google/uuid"
)

const (
	defaultEnvironment          = envDevelopment
	defaultServiceName          = "proxy"
	defaultLogLevel             = slog.LevelInfo
	defaultPort                 = "8080"
	defaultAuthGRPCAddr         = "127.0.0.1:9091"
	defaultAuthValidateTimeout  = 50 * time.Millisecond
	defaultRequestIDHeader      = "X-Request-ID"
	defaultTraceIDHeader        = "X-Trace-ID"
	defaultMaxRequestBodyBytes  = 1 * 1024 * 1024
	defaultRateLimitRPM         = 60
	defaultShutdownTimeout      = 30 * time.Second
	defaultLLMMode              = envLLMModeMock
	defaultOpenAIBaseURL        = "https://api.openai.com/v1"
	defaultOpenAIRequestTimeout = 120 * time.Second
	defaultOpenAIMaxRetries     = 3
	defaultOpenAIRetryBaseDelay = 500 * time.Millisecond
	defaultAnthropicBaseURL     = "https://api.anthropic.com"
	defaultAnthropicTimeout     = 120 * time.Second
	defaultAnthropicMaxRetries  = 3
	defaultAnthropicRetryDelay  = 500 * time.Millisecond
	defaultAuthCacheLRUCapacity = 5000
	defaultAuthCacheLRUMaxTTL   = 30 * time.Second
	defaultAuthCacheBloomItems  = 10000
	defaultAuthCacheBloomFPRate = 0.001
	maxAuthCacheLRUMaxTTL       = 30 * time.Second
	defaultDirectiveCacheTTL    = 60 * time.Second
	defaultSessionCacheTTL      = 60 * time.Second
	defaultCheckpointWorkers    = 8
	defaultCheckpointQueue      = 256
	defaultSessionGetOrCreateTO = 50 * time.Millisecond
	defaultSessionIdleTimeout   = 45 * time.Minute
	defaultSessionSweepInterval = time.Minute
	defaultIdempotencyTTL       = 24 * time.Hour
	defaultIdempotencyRedisTO   = 50 * time.Millisecond

	envDevelopment = "development"
	envStaging     = "staging"
	envProduction  = "production"
	envLLMModeMock = "mock"
	envLLMModeLive = "live"
)

// RateLimitConfig holds org-level rate limit settings (Phase 1; no DB).
type RateLimitConfig struct {
	DefaultRPM   int
	OrgOverrides map[uuid.UUID]int
}

// AuthCacheConfig holds in-process bloom + LRU settings for token validation.
type AuthCacheConfig struct {
	Enabled            bool
	LRUCapacity        int
	LRUMaxTTL          time.Duration
	BloomExpectedItems uint
	BloomFPRate        float64
}

// OpenAIConfig holds OpenAI provider settings for the proxy process.
type OpenAIConfig struct {
	APIKey         string
	BaseURL        string
	RequestTimeout time.Duration
	MaxRetries     int
	RetryBaseDelay time.Duration
	// ExtraModels are comma-sourced live-mode model IDs beyond the default OpenAI allowlist.
	ExtraModels []string
}

// AnthropicConfig holds Anthropic Messages API settings for the proxy process.
type AnthropicConfig struct {
	APIKey         string
	BaseURL        string
	RequestTimeout time.Duration
	MaxRetries     int
	RetryBaseDelay time.Duration
	ExtraModels    []string
}

type Config struct {
	Environment             string
	ServiceName             string
	LogLevel                slog.Level
	Port                    string
	RedisURL                string
	AuthGRPCAddr            string
	AuthValidateTimeout     time.Duration
	AuthCache               AuthCacheConfig
	MaxRequestBodyBytes     int64
	RequestIDHeader         string
	TraceIDHeader           string
	ErrorDocsBase           string
	RateLimit               RateLimitConfig
	ShutdownTimeout         time.Duration
	Telemetry               telemetry.Config
	LLMMode                 string
	OpenAI                  OpenAIConfig
	Anthropic               AnthropicConfig
	PostgresDSN             string
	DirectiveCacheTTL       time.Duration
	SessionCacheTTL         time.Duration
	CheckpointWorkers       int
	CheckpointQueue         int
	SessionGetOrCreateTO    time.Duration
	SessionIdleTimeout      time.Duration
	SessionSweepInterval    time.Duration
	ClickHouseDSN           string
	ClickHouseBatchSize     int
	ClickHouseFlushMS       int
	IdempotencyTTL          time.Duration
	IdempotencyRedisTimeout time.Duration
}

// ApplyDefaults fills zero-valued fields so httptest and partial Config literals behave like Load().
func (c *Config) ApplyDefaults() {
	c.applyIdentityDefaults()
	c.applyTransportDefaults()
	c.applyRateLimitDefaults()
	c.applyAuthCacheDefaults()
	c.applyLLMDefaults()
	c.applySessionDefaults()
	c.applyClickHouseDefaults()
	c.applyIdempotencyDefaults()
}

func (c *Config) applyIdempotencyDefaults() {
	applyDurationDefault(&c.IdempotencyTTL, defaultIdempotencyTTL)
	applyDurationDefault(&c.IdempotencyRedisTimeout, defaultIdempotencyRedisTO)
}

func (c *Config) applyClickHouseDefaults() {
	applyIntDefaultZeroOnly(&c.ClickHouseBatchSize, 500)
	applyIntDefaultZeroOnly(&c.ClickHouseFlushMS, 200)
}

func (c *Config) applyIdentityDefaults() {
	if strings.TrimSpace(c.Environment) == "" {
		c.Environment = defaultEnvironment
	}
	if strings.TrimSpace(c.ServiceName) == "" {
		c.ServiceName = defaultServiceName
	}
	if c.LogLevel == 0 {
		c.LogLevel = defaultLogLevel
	}
}

func (c *Config) applyTransportDefaults() {
	if strings.TrimSpace(c.Port) == "" {
		c.Port = defaultPort
	}
	if strings.TrimSpace(c.AuthGRPCAddr) == "" {
		c.AuthGRPCAddr = defaultAuthGRPCAddr
	}
	if c.AuthValidateTimeout <= 0 {
		c.AuthValidateTimeout = defaultAuthValidateTimeout
	}
	if c.MaxRequestBodyBytes < 1 {
		c.MaxRequestBodyBytes = defaultMaxRequestBodyBytes
	}
	if strings.TrimSpace(c.RequestIDHeader) == "" {
		c.RequestIDHeader = defaultRequestIDHeader
	}
	if strings.TrimSpace(c.TraceIDHeader) == "" {
		c.TraceIDHeader = defaultTraceIDHeader
	}
	if c.ShutdownTimeout <= 0 {
		c.ShutdownTimeout = defaultShutdownTimeout
	}
}

func (c *Config) applyRateLimitDefaults() {
	if c.RateLimit.DefaultRPM < 1 {
		c.RateLimit.DefaultRPM = defaultRateLimitRPM
	}
	if c.RateLimit.OrgOverrides == nil {
		c.RateLimit.OrgOverrides = map[uuid.UUID]int{}
	}
}

func (c *Config) applySessionDefaults() {
	applyDurationDefault(&c.DirectiveCacheTTL, defaultDirectiveCacheTTL)
	applyDurationDefault(&c.SessionCacheTTL, defaultSessionCacheTTL)
	applyIntDefault(&c.CheckpointWorkers, defaultCheckpointWorkers)
	applyIntDefault(&c.CheckpointQueue, defaultCheckpointQueue)
	applyDurationDefault(&c.SessionGetOrCreateTO, defaultSessionGetOrCreateTO)
	applyDurationDefaultZeroOnly(&c.SessionIdleTimeout, defaultSessionIdleTimeout)
	applyDurationDefaultZeroOnly(&c.SessionSweepInterval, defaultSessionSweepInterval)
}

// applyDurationDefault replaces non-positive durations with def (cache/timeout sanitization).
func applyDurationDefault(dst *time.Duration, def time.Duration) {
	if *dst <= 0 {
		*dst = def
	}
}

// applyDurationDefaultZeroOnly defaults only unset (zero) values so negative
// sweeper durations survive to Validate() and fail closed.
func applyDurationDefaultZeroOnly(dst *time.Duration, def time.Duration) {
	if *dst == 0 {
		*dst = def
	}
}

func applyIntDefault(dst *int, def int) {
	if *dst < 1 {
		*dst = def
	}
}

// applyIntDefaultZeroOnly defaults only unset (zero) values so explicit
// negatives survive to Validate() and fail closed.
func applyIntDefaultZeroOnly(dst *int, def int) {
	if *dst == 0 {
		*dst = def
	}
}

func (c *Config) applyAuthCacheDefaults() {
	if c.AuthCache.LRUCapacity < 1 {
		c.AuthCache.LRUCapacity = defaultAuthCacheLRUCapacity
	}
	if c.AuthCache.LRUMaxTTL <= 0 {
		c.AuthCache.LRUMaxTTL = defaultAuthCacheLRUMaxTTL
	}
	if c.AuthCache.BloomExpectedItems < 1 {
		c.AuthCache.BloomExpectedItems = defaultAuthCacheBloomItems
	}
	if c.AuthCache.BloomFPRate <= 0 || c.AuthCache.BloomFPRate >= 1 {
		c.AuthCache.BloomFPRate = defaultAuthCacheBloomFPRate
	}
}

func (c *Config) applyLLMDefaults() {
	if strings.TrimSpace(c.LLMMode) == "" {
		c.LLMMode = defaultLLMMode
	}
	c.applyOpenAIDefaults()
	c.applyAnthropicDefaults()
}

func (c *Config) applyOpenAIDefaults() {
	applyProviderHTTPDefaults(providerHTTPFields{
		BaseURL: &c.OpenAI.BaseURL, Timeout: &c.OpenAI.RequestTimeout,
		MaxRetries: &c.OpenAI.MaxRetries, RetryDelay: &c.OpenAI.RetryBaseDelay,
	}, providerHTTPFallback{
		BaseURL: defaultOpenAIBaseURL, Timeout: defaultOpenAIRequestTimeout,
		MaxRetries: defaultOpenAIMaxRetries, RetryDelay: defaultOpenAIRetryBaseDelay,
	})
}

func (c *Config) applyAnthropicDefaults() {
	applyProviderHTTPDefaults(providerHTTPFields{
		BaseURL: &c.Anthropic.BaseURL, Timeout: &c.Anthropic.RequestTimeout,
		MaxRetries: &c.Anthropic.MaxRetries, RetryDelay: &c.Anthropic.RetryBaseDelay,
	}, providerHTTPFallback{
		BaseURL: defaultAnthropicBaseURL, Timeout: defaultAnthropicTimeout,
		MaxRetries: defaultAnthropicMaxRetries, RetryDelay: defaultAnthropicRetryDelay,
	})
}

type providerHTTPFields struct {
	BaseURL    *string
	Timeout    *time.Duration
	MaxRetries *int
	RetryDelay *time.Duration
}

type providerHTTPFallback struct {
	BaseURL    string
	Timeout    time.Duration
	MaxRetries int
	RetryDelay time.Duration
}

func applyProviderHTTPDefaults(fields providerHTTPFields, fallback providerHTTPFallback) {
	if strings.TrimSpace(*fields.BaseURL) == "" {
		*fields.BaseURL = fallback.BaseURL
	}
	if *fields.Timeout <= 0 {
		*fields.Timeout = fallback.Timeout
	}
	*fields.MaxRetries = normalizeRetryCount(*fields.MaxRetries, fallback.MaxRetries)
	if *fields.RetryDelay <= 0 {
		*fields.RetryDelay = fallback.RetryDelay
	}
}

func normalizeRetryCount(current, fallback int) int {
	if current < 0 {
		return 0
	}
	if current == 0 {
		return fallback
	}
	return current
}
