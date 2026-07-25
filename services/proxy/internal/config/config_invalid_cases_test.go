package config

import (
	"time"

	"github.com/google/uuid"
)

var invalidProxyConfigCases = []struct {
	name   string
	mutate func(*Config)
}{
	{
		name: "invalid environment",
		mutate: func(c *Config) {
			c.Environment = "prod"
			c.ServiceName = "proxy"
			c.Port = "8080"
		},
	},
	{name: "invalid port", mutate: func(c *Config) { c.Port = "not-a-port" }},
	{name: "zero port", mutate: func(c *Config) { c.Port = "0" }},
	{name: "port too large", mutate: func(c *Config) { c.Port = "70000" }},
	{name: "empty service name", mutate: func(c *Config) { c.ServiceName = "  " }},
	{name: "invalid auth grpc addr", mutate: func(c *Config) { c.AuthGRPCAddr = "not-host-port" }},
	{name: "zero rate limit rpm", mutate: func(c *Config) { c.RateLimit.DefaultRPM = 0 }},
	{
		name: "auth grpc required outside development",
		mutate: func(c *Config) {
			c.Environment = "staging"
			c.AuthGRPCAddr = ""
		},
	},
	{name: "empty trace id header", mutate: func(c *Config) { c.TraceIDHeader = "" }},
	{name: "zero max body bytes", mutate: func(c *Config) { c.MaxRequestBodyBytes = 0 }},
	{name: "empty request id header", mutate: func(c *Config) { c.RequestIDHeader = "" }},
	{
		name: "org override zero rpm",
		mutate: func(c *Config) {
			orgID := uuid.MustParse("550e8400-e29b-41d4-a716-446655440000")
			c.RateLimit.OrgOverrides = map[uuid.UUID]int{orgID: 0}
		},
	},
	{name: "live mode missing openai key", mutate: func(c *Config) { c.LLMMode = "live"; c.OpenAI.APIKey = "" }},
	{name: "invalid llm mode", mutate: func(c *Config) { c.LLMMode = "invalid" }},
	{name: "auth cache zero capacity", mutate: func(c *Config) { c.AuthCache.LRUCapacity = 0 }},
	{name: "auth cache bad fp rate", mutate: func(c *Config) { c.AuthCache.BloomFPRate = 1.5 }},
	{name: "auth cache ttl above ceiling", mutate: func(c *Config) { c.AuthCache.LRUMaxTTL = 31 * time.Second }},
	{name: "session idle below sweep interval", mutate: func(c *Config) {
		c.SessionIdleTimeout = time.Second
		c.SessionSweepInterval = time.Minute
	}},
	{name: "session idle negative", mutate: func(c *Config) {
		c.SessionIdleTimeout = -time.Minute
	}},
	{name: "session sweep interval negative", mutate: func(c *Config) {
		c.SessionSweepInterval = -time.Second
	}},
	{name: "clickhouse batch size negative", mutate: func(c *Config) {
		c.ClickHouseBatchSize = -1
	}},
	{name: "clickhouse flush ms negative", mutate: func(c *Config) {
		c.ClickHouseFlushMS = -5
	}},
}
