package config

import (
	"fmt"
	"log/slog"
	"strings"
	"time"

	ibexconfig "github.com/Rick1330/ibex-harness/packages/config"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/google/uuid"
)

type envConfig struct {
	Environment           string            `env:"IBEX_ENV" envDefault:"development"`
	ServiceName           string            `env:"IBEX_SERVICE_NAME" envDefault:"proxy"`
	LogLevel              string            `env:"IBEX_LOG_LEVEL" envDefault:"INFO"`
	Port                  string            `env:"IBEX_PORT" envDefault:"8080"`
	RedisURL              ibexconfig.Secret `env:"REDIS_URL" secret:"true"`
	AuthGRPCAddr          string            `env:"IBEX_AUTH_GRPC_ADDR" envDefault:"127.0.0.1:9091"`
	AuthValidateTimeout   time.Duration     `env:"IBEX_AUTH_VALIDATE_TIMEOUT"`
	MaxRequestBodyBytes   int64             `env:"IBEX_MAX_REQUEST_BODY_BYTES"`
	RequestIDHeader       string            `env:"IBEX_REQUEST_ID_HEADER" envDefault:"X-Request-ID"`
	TraceIDHeader         string            `env:"IBEX_TRACE_ID_HEADER" envDefault:"X-Trace-ID"`
	ErrorDocsBase         string            `env:"IBEX_ERROR_DOCS_BASE"`
	RateLimitDefaultRPM   int               `env:"IBEX_RATE_LIMIT_DEFAULT_RPM"`
	RateLimitOrgOverrides string            `env:"IBEX_RATE_LIMIT_ORG_OVERRIDES"`
	ShutdownTimeoutRaw    string            `env:"IBEX_SHUTDOWN_TIMEOUT"`
	LLMMode               string            `env:"IBEX_LLM_MODE" envDefault:"mock"`
	OpenAIAPIKey          ibexconfig.Secret `env:"OPENAI_API_KEY" secret:"true"`
	OpenAIBaseURL         string            `env:"OPENAI_BASE_URL" envDefault:"https://api.openai.com/v1"`
	OpenAIRequestTimeout  time.Duration     `env:"OPENAI_REQUEST_TIMEOUT"`
	OpenAIMaxRetries      int               `env:"OPENAI_MAX_RETRIES"`
	OpenAIRetryBaseDelay  time.Duration     `env:"OPENAI_RETRY_BASE_DELAY"`
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
	}
}

func baseProxyConfig(envCfg envConfig, level slog.Level) Config {
	return Config{
		Environment:     envCfg.Environment,
		ServiceName:     envCfg.ServiceName,
		LogLevel:        level,
		Port:            envCfg.Port,
		RedisURL:        envCfg.RedisURL.String(),
		AuthGRPCAddr:    envCfg.AuthGRPCAddr,
		RequestIDHeader: envCfg.RequestIDHeader,
		TraceIDHeader:   envCfg.TraceIDHeader,
		ErrorDocsBase:   envCfg.ErrorDocsBase,
		RateLimit: RateLimitConfig{
			DefaultRPM:   defaultRateLimitRPM,
			OrgOverrides: map[uuid.UUID]int{},
		},
		LLMMode: strings.TrimSpace(envCfg.LLMMode),
		OpenAI:  openAIConfigFromEnv(envCfg),
	}
}

func applyProxyEnvOverrides(cfg *Config, envCfg envConfig) error {
	if envCfg.AuthValidateTimeout > 0 {
		cfg.AuthValidateTimeout = envCfg.AuthValidateTimeout
	}
	if envCfg.MaxRequestBodyBytes > 0 {
		cfg.MaxRequestBodyBytes = envCfg.MaxRequestBodyBytes
	}
	if envCfg.RateLimitDefaultRPM > 0 {
		cfg.RateLimit.DefaultRPM = envCfg.RateLimitDefaultRPM
	}
	timeout, err := ibexconfig.ParseShutdownTimeout(envCfg.ShutdownTimeoutRaw, 0)
	if err != nil {
		return err
	}
	if timeout > 0 {
		cfg.ShutdownTimeout = timeout
	}
	return applyRateLimitOverrides(cfg, envCfg.RateLimitOrgOverrides)
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
