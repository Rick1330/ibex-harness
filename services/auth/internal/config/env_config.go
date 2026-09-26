package config

import (
	"fmt"
	"log/slog"
	"strings"
	"time"

	ibexconfig "github.com/Rick1330/ibex-harness/packages/config"
	"github.com/Rick1330/ibex-harness/packages/crypto"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
)

type envConfig struct {
	Environment            string            `env:"IBEX_ENV" envDefault:"development"`
	ServiceName            string            `env:"IBEX_SERVICE_NAME" envDefault:"auth"`
	LogLevel               string            `env:"IBEX_LOG_LEVEL" envDefault:"INFO"`
	Port                   string            `env:"IBEX_PORT" envDefault:"8081"`
	GRPCPort               string            `env:"IBEX_GRPC_PORT" envDefault:"9091"`
	PostgresDSN            ibexconfig.Secret `env:"POSTGRES_DSN,required" secret:"true"`
	RedisURL               ibexconfig.Secret `env:"REDIS_URL" secret:"true"`
	ValidateTokenRPM       int64             `env:"IBEX_AUTH_VALIDATE_RPM" envDefault:"6000"`
	CredentialsMasterKey   ibexconfig.Secret `env:"IBEX_CREDENTIALS_MASTER_KEY" secret:"true"`
	CredentialsMasterKeyID string            `env:"IBEX_CREDENTIALS_MASTER_KEY_ID" envDefault:"v1"`
	TOTPEnabled            bool              `env:"IBEX_AUTH_TOTP_ENABLED" envDefault:"false"`
	JWTPrivateKeyPEM       ibexconfig.Secret `env:"JWT_PRIVATE_KEY_PEM" secret:"true"`
	JWTIssuer              string            `env:"JWT_ISSUER" envDefault:"ibex-harness"`
	JWTAudience            string            `env:"JWT_AUDIENCE" envDefault:"ibex-dashboard"`
	JWTAccessTTLRaw        string            `env:"JWT_ACCESS_TOKEN_TTL"`
	JWTRefreshTTLRaw       string            `env:"JWT_REFRESH_TOKEN_TTL"`
	JWTStepUpTTLRaw        string            `env:"JWT_STEP_UP_TOKEN_TTL"`
	AuthServiceToken       ibexconfig.Secret `env:"IBEX_AUTH_SERVICE_TOKEN" secret:"true"`
	ShutdownTimeoutRaw     string            `env:"IBEX_SHUTDOWN_TIMEOUT"`
	Argon2MemoryKiB        uint32            `env:"IBEX_ARGON2_MEMORY_KIB"`
	Argon2Time             uint32            `env:"IBEX_ARGON2_TIME"`
	Argon2Parallelism      uint8             `env:"IBEX_ARGON2_PARALLELISM"`
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

	cfg, err := baseAuthConfig(envCfg, level)
	if err != nil {
		return Config{}, err
	}
	return finalizeAuthConfig(cfg, envCfg)
}

func baseAuthConfig(envCfg envConfig, level slog.Level) (Config, error) {
	cfg := Config{
		Environment:            envCfg.Environment,
		ServiceName:            envCfg.ServiceName,
		LogLevel:               level,
		Port:                   envCfg.Port,
		GRPCPort:               envCfg.GRPCPort,
		PostgresDSN:            envCfg.PostgresDSN.String(),
		RedisURL:               envCfg.RedisURL.String(),
		ValidateTokenRPM:       envCfg.ValidateTokenRPM,
		CredentialsMasterKey:   envCfg.CredentialsMasterKey.String(),
		CredentialsMasterKeyID: credentialKeyID(envCfg.CredentialsMasterKeyID),
		TOTPEnabled:            envCfg.TOTPEnabled,
		JWTPrivateKeyPEM:       envCfg.JWTPrivateKeyPEM.String(),
		JWTIssuer:              strings.TrimSpace(envCfg.JWTIssuer),
		JWTAudience:            strings.TrimSpace(envCfg.JWTAudience),
		AuthServiceToken:       strings.TrimSpace(envCfg.AuthServiceToken.String()),
		Argon2:                 crypto.ProductionParams(),
	}
	if err := applyAuthEnvOverrides(&cfg, envCfg); err != nil {
		return Config{}, err
	}
	return cfg, nil
}

func applyAuthEnvOverrides(cfg *Config, envCfg envConfig) error {
	timeout, err := ibexconfig.ParseShutdownTimeout(envCfg.ShutdownTimeoutRaw, defaultShutdownTimeout)
	if err != nil {
		return err
	}
	cfg.ShutdownTimeout = timeout
	applyArgon2Overrides(&cfg.Argon2, envCfg)
	cfg.JWTAccessTTL, err = parseDurationOr(envCfg.JWTAccessTTLRaw, 15*time.Minute)
	if err != nil {
		return fmt.Errorf("JWT_ACCESS_TOKEN_TTL: %w", err)
	}
	cfg.JWTRefreshTTL, err = parseDurationOr(envCfg.JWTRefreshTTLRaw, 7*24*time.Hour)
	if err != nil {
		return fmt.Errorf("JWT_REFRESH_TOKEN_TTL: %w", err)
	}
	cfg.JWTStepUpTTL, err = parseDurationOr(envCfg.JWTStepUpTTLRaw, 5*time.Minute)
	if err != nil {
		return fmt.Errorf("JWT_STEP_UP_TOKEN_TTL: %w", err)
	}
	return nil
}

func parseDurationOr(raw string, fallback time.Duration) (time.Duration, error) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return fallback, nil
	}
	d, err := time.ParseDuration(raw)
	if err != nil {
		return 0, err
	}
	if d <= 0 {
		return 0, fmt.Errorf("duration must be positive")
	}
	return d, nil
}

func applyArgon2Overrides(params *token.Argon2Params, envCfg envConfig) {
	if envCfg.Argon2MemoryKiB > 0 {
		params.MemoryKiB = envCfg.Argon2MemoryKiB
	}
	if envCfg.Argon2Time > 0 {
		params.Time = envCfg.Argon2Time
	}
	if envCfg.Argon2Parallelism > 0 {
		params.Parallelism = envCfg.Argon2Parallelism
	}
}

func finalizeAuthConfig(cfg Config, envCfg envConfig) (Config, error) {
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

func credentialKeyID(raw string) string {
	if id := strings.TrimSpace(raw); id != "" {
		return id
	}
	return "v1"
}
