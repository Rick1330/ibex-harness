package config

import (
	"fmt"
	"log/slog"
	"net"
	"strconv"
	"strings"
	"time"

	"github.com/Rick1330/ibex-harness/packages/crypto"
	"github.com/Rick1330/ibex-harness/packages/policysnapshot"
	"github.com/Rick1330/ibex-harness/packages/shutdown"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
)

const (
	defaultEnvironment     = "development"
	defaultServiceName     = "auth"
	defaultLogLevel        = slog.LevelInfo
	defaultPort            = "8081"
	defaultGRPCPort        = "9091"
	defaultShutdownTimeout = 30 * time.Second
)

type Config struct {
	Environment            string
	ServiceName            string
	LogLevel               slog.Level
	Port                   string
	GRPCPort               string
	PostgresDSN            string
	RedisURL               string
	ValidateTokenRPM       int64
	CredentialsMasterKey   string
	CredentialsMasterKeyID string
	TOTPEnabled            bool
	JWTPrivateKeyPEM       string
	JWTIssuer              string
	JWTAudience            string
	JWTAccessTTL           time.Duration
	JWTRefreshTTL          time.Duration
	JWTStepUpTTL           time.Duration
	AuthServiceToken       string
	PolicySigningKeyPEM    string
	PolicySigningKeyID     string
	PolicyEpoch            int64
	Argon2                 token.Argon2Params
	ShutdownTimeout        time.Duration
	Telemetry              telemetry.Config
}

func Load() (Config, error) {
	return loadFromEnv()
}

func (c Config) Validate() error {
	checks := []func() error{
		func() error { return validateEnvironment(c) },
		func() error { return validateServiceName(c) },
		func() error { return validateTCPPort("IBEX_PORT", c.Port) },
		func() error { return validateTCPPort("IBEX_GRPC_PORT", c.GRPCPort) },
		func() error { return validatePostgresDSN(c) },
		func() error { return validateCredentialsMasterKey(c) },
		func() error { return validateTOTPSessionConfig(c) },
		func() error { return validateAuthServiceToken(c) },
		func() error { return validatePolicySigningConfig(c) },
		func() error { return validateValidateTokenRPM(c.ValidateTokenRPM) },
		func() error { return shutdown.ValidateTimeout(c.ShutdownTimeout) },
	}
	for _, check := range checks {
		if err := check(); err != nil {
			return err
		}
	}
	return nil
}

func validateAuthServiceToken(c Config) error {
	if !requiresAuthServiceToken(c) {
		return nil
	}
	if strings.TrimSpace(c.AuthServiceToken) == "" {
		return fmt.Errorf("IBEX_AUTH_SERVICE_TOKEN is required when operator sessions are enabled outside development")
	}
	return nil
}

// validatePolicySigningConfig requires and validates the AuthService
// policy-signing key outside development (GAP-002, decision record 21 §2.1).
func validatePolicySigningConfig(c Config) error {
	if strings.TrimSpace(c.PolicySigningKeyPEM) == "" {
		if c.Environment == "development" {
			return nil
		}
		return fmt.Errorf("IBEX_AUTH_POLICY_SIGNING_KEY_PEM is required outside development")
	}
	if _, err := policysnapshot.NewIssuer(c.PolicyIssuerConfig()); err != nil {
		return fmt.Errorf("IBEX_AUTH_POLICY_SIGNING_KEY_PEM: %w", err)
	}
	return nil
}

// PolicyIssuerConfig normalizes policy-signing settings for Issuer
// construction: an unset key id defaults to v1 and an unset epoch to 1.
func (c Config) PolicyIssuerConfig() policysnapshot.IssuerConfig {
	keyID := strings.TrimSpace(c.PolicySigningKeyID)
	if keyID == "" {
		keyID = "v1"
	}
	epoch := c.PolicyEpoch
	if epoch == 0 {
		epoch = 1
	}
	return policysnapshot.IssuerConfig{
		PrivateKeyPEM: strings.TrimSpace(c.PolicySigningKeyPEM),
		KeyID:         keyID,
		Epoch:         epoch,
	}
}

func requiresAuthServiceToken(c Config) bool {
	if c.Environment == "development" {
		return false
	}
	return c.TOTPEnabled || strings.TrimSpace(c.JWTPrivateKeyPEM) != ""
}

func validateServiceName(c Config) error {
	if strings.TrimSpace(c.ServiceName) == "" {
		return fmt.Errorf("IBEX_SERVICE_NAME must not be empty")
	}
	return nil
}

func validatePostgresDSN(c Config) error {
	if c.PostgresDSN == "" {
		return fmt.Errorf("POSTGRES_DSN is required for auth token validation")
	}
	return nil
}

func validateTOTPSessionConfig(c Config) error {
	if !c.TOTPEnabled {
		return nil
	}
	required := []struct {
		name  string
		value string
	}{
		{"IBEX_CREDENTIALS_MASTER_KEY", c.CredentialsMasterKey},
		{"JWT_PRIVATE_KEY_PEM", c.JWTPrivateKeyPEM},
		{"JWT_ISSUER", c.JWTIssuer},
		{"JWT_AUDIENCE", c.JWTAudience},
	}
	for _, field := range required {
		if strings.TrimSpace(field.value) == "" {
			return fmt.Errorf("%s is required when IBEX_AUTH_TOTP_ENABLED=true", field.name)
		}
	}
	return nil
}

func validateCredentialsMasterKey(c Config) error {
	raw := strings.TrimSpace(c.CredentialsMasterKey)
	if raw == "" {
		if c.Environment == "production" {
			return fmt.Errorf("IBEX_CREDENTIALS_MASTER_KEY is required when IBEX_ENV=production")
		}
		return nil
	}
	if _, err := crypto.ParseMasterKeyBase64(raw); err != nil {
		return fmt.Errorf("IBEX_CREDENTIALS_MASTER_KEY: %w", err)
	}
	return nil
}

func validateEnvironment(c Config) error {
	switch c.Environment {
	case "development", "staging", "production":
		return nil
	default:
		return fmt.Errorf("IBEX_ENV must be one of development, staging, production")
	}
}

func validateTCPPort(name, port string) error {
	portNum, err := strconv.Atoi(port)
	if err != nil || portNum < 1 || portNum > 65535 {
		return fmt.Errorf("%s must be a valid TCP port", name)
	}
	return nil
}

func validateValidateTokenRPM(rpm int64) error {
	if rpm < 1 {
		return fmt.Errorf("IBEX_AUTH_VALIDATE_RPM must be >= 1")
	}
	return nil
}

func ListenAddress(port string) string {
	return net.JoinHostPort("", port)
}
