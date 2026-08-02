package config

import (
	"fmt"
	"log/slog"
	"net"
	"strconv"
	"strings"
	"time"

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
	Environment      string
	ServiceName      string
	LogLevel         slog.Level
	Port             string
	GRPCPort         string
	PostgresDSN      string
	RedisURL         string
	ValidateTokenRPM int64
	Argon2           token.Argon2Params
	ShutdownTimeout  time.Duration
	Telemetry        telemetry.Config
}

func Load() (Config, error) {
	return loadFromEnv()
}

func (c Config) Validate() error {
	if err := validateEnvironment(c.Environment); err != nil {
		return err
	}
	if strings.TrimSpace(c.ServiceName) == "" {
		return fmt.Errorf("IBEX_SERVICE_NAME must not be empty")
	}
	if err := validateTCPPort("IBEX_PORT", c.Port); err != nil {
		return err
	}
	if err := validateTCPPort("IBEX_GRPC_PORT", c.GRPCPort); err != nil {
		return err
	}
	if c.PostgresDSN == "" {
		return fmt.Errorf("POSTGRES_DSN is required for auth token validation")
	}
	if err := validateValidateTokenRPM(c.ValidateTokenRPM); err != nil {
		return err
	}
	return shutdown.ValidateTimeout(c.ShutdownTimeout)
}

func validateEnvironment(env string) error {
	switch env {
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
