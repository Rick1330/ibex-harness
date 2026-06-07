package config

import (
	"log/slog"
	"strings"
	"time"

	"github.com/google/uuid"
)

const (
	defaultEnvironment         = "development"
	defaultServiceName         = "proxy"
	defaultLogLevel            = slog.LevelInfo
	defaultPort                = "8080"
	defaultAuthGRPCAddr        = "127.0.0.1:9091"
	defaultAuthValidateTimeout = 50 * time.Millisecond
	defaultRequestIDHeader     = "X-Request-ID"
	defaultTraceIDHeader       = "X-Trace-ID"
	defaultMaxRequestBodyBytes = 1 * 1024 * 1024
	defaultRateLimitRPM        = 60
)

// RateLimitConfig holds org-level rate limit settings (Phase 1; no DB).
type RateLimitConfig struct {
	DefaultRPM   int
	OrgOverrides map[uuid.UUID]int
}

type Config struct {
	Environment         string
	ServiceName         string
	LogLevel            slog.Level
	Port                string
	RedisURL            string
	AuthGRPCAddr        string
	AuthValidateTimeout time.Duration
	MaxRequestBodyBytes int64
	RequestIDHeader     string
	TraceIDHeader       string
	ErrorDocsBase       string
	RateLimit           RateLimitConfig
}

// ApplyDefaults fills zero-valued fields so httptest and partial Config literals behave like Load().
func (c *Config) ApplyDefaults() {
	if strings.TrimSpace(c.Environment) == "" {
		c.Environment = defaultEnvironment
	}
	if strings.TrimSpace(c.ServiceName) == "" {
		c.ServiceName = defaultServiceName
	}
	if c.LogLevel == 0 {
		c.LogLevel = defaultLogLevel
	}
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
	if c.RateLimit.DefaultRPM < 1 {
		c.RateLimit.DefaultRPM = defaultRateLimitRPM
	}
	if c.RateLimit.OrgOverrides == nil {
		c.RateLimit.OrgOverrides = map[uuid.UUID]int{}
	}
}
