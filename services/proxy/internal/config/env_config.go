package config

import (
	"fmt"
	"log/slog"
	"os"
	"strings"
	"time"

	ibexconfig "github.com/Rick1330/ibex-harness/packages/config"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/google/uuid"
)

type envConfig struct {
	Environment             string            `env:"IBEX_ENV" envDefault:"development"`
	ServiceName             string            `env:"IBEX_SERVICE_NAME" envDefault:"proxy"`
	LogLevel                string            `env:"IBEX_LOG_LEVEL" envDefault:"INFO"`
	Port                    string            `env:"IBEX_PORT" envDefault:"8080"`
	RedisURL                ibexconfig.Secret `env:"REDIS_URL" secret:"true"`
	AuthGRPCAddr            string            `env:"IBEX_AUTH_GRPC_ADDR" envDefault:"127.0.0.1:9091"`
	AuthValidateTimeout     time.Duration     `env:"IBEX_AUTH_VALIDATE_TIMEOUT"`
	ContextGRPCTarget       string            `env:"IBEX_CONTEXT_GRPC_TARGET"`
	ContextAssembleTimeout  time.Duration     `env:"IBEX_CONTEXT_ASSEMBLE_TIMEOUT"`
	ContextEnabled          string            `env:"IBEX_CONTEXT_ENABLED" envDefault:"false"`
	ContextEmbedMetadata    string            `env:"IBEX_CONTEXT_EMBED_METADATA" envDefault:"false"`
	MaxRequestBodyBytes     int64             `env:"IBEX_MAX_REQUEST_BODY_BYTES"`
	RequestIDHeader         string            `env:"IBEX_REQUEST_ID_HEADER" envDefault:"X-Request-ID"`
	TraceIDHeader           string            `env:"IBEX_TRACE_ID_HEADER" envDefault:"X-Trace-ID"`
	ErrorDocsBase           string            `env:"IBEX_ERROR_DOCS_BASE"`
	RateLimitDefaultRPM     int               `env:"IBEX_RATE_LIMIT_DEFAULT_RPM"`
	RateLimitOrgOverrides   string            `env:"IBEX_RATE_LIMIT_ORG_OVERRIDES"`
	ShutdownTimeoutRaw      string            `env:"IBEX_SHUTDOWN_TIMEOUT"`
	LLMMode                 string            `env:"IBEX_LLM_MODE" envDefault:"mock"`
	LLMExtraModels          string            `env:"IBEX_LLM_EXTRA_MODELS"`
	OpenAIAPIKey            ibexconfig.Secret `env:"OPENAI_API_KEY" secret:"true"`
	OpenAIBaseURL           string            `env:"OPENAI_BASE_URL" envDefault:"https://api.openai.com/v1"`
	OpenAIRequestTimeout    time.Duration     `env:"OPENAI_REQUEST_TIMEOUT"`
	OpenAIMaxRetries        int               `env:"OPENAI_MAX_RETRIES"`
	OpenAIRetryBaseDelay    time.Duration     `env:"OPENAI_RETRY_BASE_DELAY"`
	AnthropicAPIKey         ibexconfig.Secret `env:"ANTHROPIC_API_KEY" secret:"true"`
	AnthropicBaseURL        string            `env:"ANTHROPIC_BASE_URL" envDefault:"https://api.anthropic.com"`
	AnthropicRequestTO      time.Duration     `env:"ANTHROPIC_REQUEST_TIMEOUT"`
	AnthropicMaxRetries     int               `env:"ANTHROPIC_MAX_RETRIES"`
	AnthropicRetryDelay     time.Duration     `env:"ANTHROPIC_RETRY_BASE_DELAY"`
	AnthropicExtraModels    string            `env:"ANTHROPIC_EXTRA_MODELS"`
	ModelCapabilityOverlays string            `env:"IBEX_MODEL_CAPABILITY_OVERLAYS"`
	SelfHostedEnabled       string            `env:"IBEX_SELFHOSTED_ENABLED" envDefault:"false"`
	SelfHostedBaseURL       string            `env:"IBEX_SELFHOSTED_BASE_URL"`
	SelfHostedModels        string            `env:"IBEX_SELFHOSTED_MODELS"`
	SelfHostedAPIKey        ibexconfig.Secret `env:"IBEX_SELFHOSTED_API_KEY" secret:"true"`
	SelfHostedReadyTimeout  time.Duration     `env:"IBEX_SELFHOSTED_READY_TIMEOUT"`
	SelfHostedReadyPoll     time.Duration     `env:"IBEX_SELFHOSTED_READY_POLL"`
	ProviderBreakerFailures uint32            `env:"IBEX_PROVIDER_CIRCUIT_BREAKER_FAILURES"`
	ProviderBreakerCoolSecs int               `env:"IBEX_PROVIDER_CIRCUIT_BREAKER_COOLDOWN_SECONDS"`
	AuthCacheEnabled        string            `env:"IBEX_AUTH_CACHE_ENABLED" envDefault:"true"`
	AuthCacheLRUCapacity    int               `env:"IBEX_AUTH_CACHE_LRU_CAPACITY"`
	AuthCacheLRUMaxTTL      time.Duration     `env:"IBEX_AUTH_CACHE_LRU_MAX_TTL"`
	AuthCacheBloomItems     uint              `env:"IBEX_AUTH_CACHE_BLOOM_EXPECTED_ITEMS"`
	AuthCacheBloomFPRate    float64           `env:"IBEX_AUTH_CACHE_BLOOM_FP_RATE"`
	PostgresDSN             ibexconfig.Secret `env:"POSTGRES_DSN" secret:"true"`
	DirectiveCacheTTL       time.Duration     `env:"IBEX_DIRECTIVE_CACHE_TTL"`
	SessionCacheTTL         time.Duration     `env:"IBEX_SESSION_CACHE_TTL"`
	CheckpointWorkers       int               `env:"IBEX_SESSION_CHECKPOINT_WORKERS"`
	CheckpointQueue         int               `env:"IBEX_SESSION_CHECKPOINT_QUEUE"`
	SessionGetOrCreateTO    time.Duration     `env:"IBEX_SESSION_GETORCREATE_TIMEOUT"`
	SessionIdleTimeout      time.Duration     `env:"IBEX_SESSION_IDLE_TIMEOUT"`
	SessionSweepInterval    time.Duration     `env:"IBEX_SESSION_SWEEP_INTERVAL"`
	ClickHouseDSN           ibexconfig.Secret `env:"CLICKHOUSE_DSN" secret:"true"`
	ClickHouseBatchSize     int               `env:"CLICKHOUSE_INSERT_BATCH_SIZE"`
	ClickHouseFlushMS       int               `env:"CLICKHOUSE_INSERT_FLUSH_MS"`
	IdempotencyTTL          time.Duration     `env:"IBEX_IDEMPOTENCY_TTL"`
	IdempotencyRedisTO      time.Duration     `env:"IBEX_IDEMPOTENCY_REDIS_TIMEOUT"`
	ExtractionTurnsTTL      time.Duration     `env:"IBEX_EXTRACTION_TURNS_TTL"`
	WorkerEnqueueBaseURL    string            `env:"IBEX_WORKER_ENQUEUE_BASE_URL"`
	WorkerEnqueueAPIToken   ibexconfig.Secret `env:"IBEX_WORKER_ENQUEUE_API_TOKEN" secret:"true"`
	TokenizerMode           string            `env:"IBEX_TOKENIZER_MODE" envDefault:"local"`
	TokenizerAssetDir       string            `env:"IBEX_TOKENIZER_ASSET_DIR"`
}

func loadFromEnv() (Config, error) {
	envCfg, err := ibexconfig.Load[envConfig]()
	if err != nil {
		return Config{}, err
	}

	level, err := parseLogLevel(envCfg.LogLevel)
	if err != nil {
		return Config{}, err
	}

	cfg := baseProxyConfig(envCfg, level)
	sh, err := selfHostedConfigFromEnv(envCfg)
	if err != nil {
		return Config{}, err
	}
	cfg.SelfHosted = sh
	cfg.ProviderBreakerFailures = envCfg.ProviderBreakerFailures
	cfg.ProviderBreakerCoolDown = cooldownFromSeconds(envCfg.ProviderBreakerCoolSecs)
	overlays, err := ParseCapabilityOverlays(envCfg.ModelCapabilityOverlays)
	if err != nil {
		return Config{}, err
	}
	cfg.ModelCapabilityOverlays = overlays
	cfg.Tokenizer = TokenizerConfig{
		Mode:     envCfg.TokenizerMode,
		AssetDir: envCfg.TokenizerAssetDir,
	}
	if err := applyProxyEnvOverrides(&cfg, envCfg); err != nil {
		return Config{}, err
	}
	return finalizeProxyConfig(cfg, envCfg)
}

func openAIConfigFromEnv(envCfg envConfig) OpenAIConfig {
	return OpenAIConfig{
		APIKey:         envCfg.OpenAIAPIKey.String(),
		BaseURL:        envCfg.OpenAIBaseURL,
		RequestTimeout: envCfg.OpenAIRequestTimeout,
		MaxRetries:     envCfg.OpenAIMaxRetries,
		RetryBaseDelay: envCfg.OpenAIRetryBaseDelay,
		ExtraModels:    parseCSVModels(envCfg.LLMExtraModels),
	}
}

func anthropicConfigFromEnv(envCfg envConfig) AnthropicConfig {
	cfg := AnthropicConfig{APIKey: envCfg.AnthropicAPIKey.String()}
	cfg.BaseURL = envCfg.AnthropicBaseURL
	cfg.RequestTimeout = envCfg.AnthropicRequestTO
	cfg.MaxRetries = envCfg.AnthropicMaxRetries
	cfg.RetryBaseDelay = envCfg.AnthropicRetryDelay
	cfg.ExtraModels = parseCSVModels(envCfg.AnthropicExtraModels)
	return cfg
}

func selfHostedConfigFromEnv(envCfg envConfig) (SelfHostedConfig, error) {
	enabled, err := parseEnabledFlag(envCfg.SelfHostedEnabled, false)
	if err != nil {
		return SelfHostedConfig{}, fmt.Errorf("IBEX_SELFHOSTED_ENABLED: %w", err)
	}
	return SelfHostedConfig{
		Enabled:      enabled,
		BaseURL:      envCfg.SelfHostedBaseURL,
		APIKey:       envCfg.SelfHostedAPIKey.String(),
		Models:       parseCSVModels(envCfg.SelfHostedModels),
		ReadyTimeout: envCfg.SelfHostedReadyTimeout,
		ReadyPoll:    envCfg.SelfHostedReadyPoll,
	}, nil
}

func cooldownFromSeconds(secs int) time.Duration {
	// Max seconds that fit in time.Duration without overflow (math.MaxInt64 / 1e9).
	const maxCooldownSeconds = 9223372036
	if secs <= 0 || secs > maxCooldownSeconds {
		return 0
	}
	return time.Duration(secs) * time.Second
}

func parseCSVModels(raw string) []string {
	parts := strings.Split(raw, ",")
	out := make([]string, 0, len(parts))
	seen := make(map[string]struct{}, len(parts))
	for _, p := range parts {
		m := strings.TrimSpace(p)
		if m == "" {
			continue
		}
		if _, ok := seen[m]; ok {
			continue
		}
		seen[m] = struct{}{}
		out = append(out, m)
	}
	return out
}

func baseProxyConfig(envCfg envConfig, level slog.Level) Config {
	return Config{
		Environment:       envCfg.Environment,
		ServiceName:       envCfg.ServiceName,
		LogLevel:          level,
		Port:              envCfg.Port,
		RedisURL:          envCfg.RedisURL.String(),
		AuthGRPCAddr:      envCfg.AuthGRPCAddr,
		ContextGRPCTarget: envCfg.ContextGRPCTarget,
		RequestIDHeader:   envCfg.RequestIDHeader,
		TraceIDHeader:     envCfg.TraceIDHeader,
		ErrorDocsBase:     envCfg.ErrorDocsBase,
		RateLimit: RateLimitConfig{
			DefaultRPM:   defaultRateLimitRPM,
			OrgOverrides: map[uuid.UUID]int{},
		},
		LLMMode:   strings.TrimSpace(envCfg.LLMMode),
		OpenAI:    openAIConfigFromEnv(envCfg),
		Anthropic: anthropicConfigFromEnv(envCfg),
		AuthCache: AuthCacheConfig{
			Enabled: true,
		},
		PostgresDSN:             envCfg.PostgresDSN.String(),
		DirectiveCacheTTL:       envCfg.DirectiveCacheTTL,
		SessionCacheTTL:         envCfg.SessionCacheTTL,
		CheckpointWorkers:       envCfg.CheckpointWorkers,
		CheckpointQueue:         envCfg.CheckpointQueue,
		SessionGetOrCreateTO:    envCfg.SessionGetOrCreateTO,
		SessionIdleTimeout:      envCfg.SessionIdleTimeout,
		SessionSweepInterval:    envCfg.SessionSweepInterval,
		ClickHouseDSN:           envCfg.ClickHouseDSN.String(),
		ClickHouseBatchSize:     envCfg.ClickHouseBatchSize,
		ClickHouseFlushMS:       envCfg.ClickHouseFlushMS,
		IdempotencyTTL:          envCfg.IdempotencyTTL,
		IdempotencyRedisTimeout: envCfg.IdempotencyRedisTO,
		ExtractionTurnsTTL:      envCfg.ExtractionTurnsTTL,
		WorkerEnqueueBaseURL:    strings.TrimSpace(envCfg.WorkerEnqueueBaseURL),
		WorkerEnqueueAPIToken:   envCfg.WorkerEnqueueAPIToken.String(),
	}
}

func applyProxyEnvOverrides(cfg *Config, envCfg envConfig) error {
	applyProxyNumericEnv(cfg, envCfg)
	if err := applyContextEnabledEnv(cfg, envCfg); err != nil {
		return err
	}
	if err := applyContextEmbedMetadataEnv(cfg, envCfg); err != nil {
		return err
	}
	if err := applyProxyShutdownEnv(cfg, envCfg); err != nil {
		return err
	}
	if err := applyAuthCacheEnv(cfg, envCfg); err != nil {
		return err
	}
	return applyRateLimitOverrides(cfg, envCfg.RateLimitOrgOverrides)
}

func applyProxyNumericEnv(cfg *Config, envCfg envConfig) {
	if envCfg.AuthValidateTimeout > 0 {
		cfg.AuthValidateTimeout = envCfg.AuthValidateTimeout
	}
	if envCfg.ContextAssembleTimeout > 0 {
		cfg.ContextAssembleTimeout = envCfg.ContextAssembleTimeout
	}
	if envCfg.MaxRequestBodyBytes > 0 {
		cfg.MaxRequestBodyBytes = envCfg.MaxRequestBodyBytes
	}
	if envCfg.RateLimitDefaultRPM > 0 {
		cfg.RateLimit.DefaultRPM = envCfg.RateLimitDefaultRPM
	}
}

func applyProxyShutdownEnv(cfg *Config, envCfg envConfig) error {
	timeout, err := ibexconfig.ParseShutdownTimeout(envCfg.ShutdownTimeoutRaw, 0)
	if err != nil {
		return err
	}
	if timeout > 0 {
		cfg.ShutdownTimeout = timeout
	}
	return nil
}

func applyContextEnabledEnv(cfg *Config, envCfg envConfig) error {
	enabled, err := parseEnabledFlag(envCfg.ContextEnabled, false)
	if err != nil {
		return fmt.Errorf("IBEX_CONTEXT_ENABLED: %w", err)
	}
	cfg.ContextEnabled = enabled
	return nil
}

func applyContextEmbedMetadataEnv(cfg *Config, envCfg envConfig) error {
	enabled, err := parseEnabledFlag(envCfg.ContextEmbedMetadata, false)
	if err != nil {
		return fmt.Errorf("IBEX_CONTEXT_EMBED_METADATA: %w", err)
	}
	cfg.ContextEmbedMetadata = enabled
	return nil
}

func applyAuthCacheEnv(cfg *Config, envCfg envConfig) error {
	enabled, err := parseEnabledFlag(envCfg.AuthCacheEnabled, true)
	if err != nil {
		return fmt.Errorf("IBEX_AUTH_CACHE_ENABLED: %w", err)
	}
	cfg.AuthCache.Enabled = enabled
	if envCfg.AuthCacheLRUCapacity > 0 {
		cfg.AuthCache.LRUCapacity = envCfg.AuthCacheLRUCapacity
	}
	if envCfg.AuthCacheLRUMaxTTL > 0 {
		cfg.AuthCache.LRUMaxTTL = envCfg.AuthCacheLRUMaxTTL
	}
	if envCfg.AuthCacheBloomItems > 0 {
		cfg.AuthCache.BloomExpectedItems = envCfg.AuthCacheBloomItems
	}
	if envCfg.AuthCacheBloomFPRate > 0 {
		cfg.AuthCache.BloomFPRate = envCfg.AuthCacheBloomFPRate
	}
	return nil
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

func applyRateLimitOverrides(cfg *Config, raw string) error {
	if strings.TrimSpace(raw) == "" {
		return nil
	}
	overrides, err := parseOrgRPMOverrides(raw)
	if err != nil {
		return fmt.Errorf("IBEX_RATE_LIMIT_ORG_OVERRIDES: %w", err)
	}
	cfg.RateLimit.OrgOverrides = overrides
	return nil
}

func finalizeProxyConfig(cfg Config, envCfg envConfig) (Config, error) {
	cfg.ApplyDefaults()
	applyUnsetContextGRPCTargetDefault(&cfg)

	telemetryCfg, err := telemetry.ConfigFromEnv(cfg.ServiceName, cfg.Environment)
	if err != nil {
		return Config{}, err
	}
	cfg.Telemetry = telemetryCfg

	if err := cfg.Validate(); err != nil {
		return Config{}, err
	}
	ibexconfig.LogDebug(envCfg)
	return cfg, nil
}

// applyUnsetContextGRPCTargetDefault sets the dial target only when the env var is
// absent. An explicitly empty IBEX_CONTEXT_GRPC_TARGET stays empty so dial is skipped.
func applyUnsetContextGRPCTargetDefault(cfg *Config) {
	if _, set := os.LookupEnv("IBEX_CONTEXT_GRPC_TARGET"); set {
		return
	}
	if cfg.ContextGRPCTarget == "" {
		cfg.ContextGRPCTarget = defaultContextGRPCTarget
	}
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
