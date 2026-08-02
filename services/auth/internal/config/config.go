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
	defaultEnvironment      = "development"
	defaultServiceName      = "auth"
	defaultLogLevel         = slog.LevelInfo
	defaultPort             = "8081"
	defaultGRPCPort         = "9091"
	defaultShutdownTimeout  = 30 * time.Second
	defaultValidateTokenRPM = int64(6000)
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
	switch c.Environment {
	case "development", "staging", "production":
	default:
		return fmt.Errorf("IBEX_ENV must be one of development, staging, production")
	}
	if strings.TrimSpace(c.ServiceName) == "" {
		return fmt.Errorf("IBEX_SERVICE_NAME must not be empty")
	}
	for name, port := range map[string]string{"IBEX_PORT": c.Port, "IBEX_GRPC_PORT": c.GRPCPort} {
		portNum, err := strconv.Atoi(port)
		if err != nil || portNum < 1 || portNum > 65535 {
			return fmt.Errorf("%s must be a valid TCP port", name)
		}
	}
	if c.PostgresDSN == "" {
		return fmt.Errorf("POSTGRES_DSN is required for auth token validation")
	}
	if c.ValidateTokenRPM < 1 {
		return fmt.Errorf("IBEX_AUTH_VALIDATE_RPM must be >= 1")
	}
	return shutdown.ValidateTimeout(c.ShutdownTimeout)
}

func ListenAddress(port string) string {
	return net.JoinHostPort("", port)
}
