package config

import (
	"strings"
	"testing"
)

// testContextServiceToken is a stand-in for IBEX_CONTEXT_GRPC_SERVICE_TOKEN.
const testContextServiceToken = "0123456789abcdef0123456789abcdef"

// contextAuthCase is one row of the ADR-0096 caller-auth config matrix.
type contextAuthCase struct {
	name        string
	environment string
	enabled     bool
	target      string
	token       string
	wantErr     string // substring; empty means the config must validate
}

func contextAuthConfig(tc contextAuthCase) Config {
	return Config{
		Environment:             tc.environment,
		ContextEnabled:          tc.enabled,
		ContextGRPCTarget:       tc.target,
		ContextGRPCServiceToken: tc.token,
		ContextAssembleTimeout:  defaultContextAssembleTimeout,
	}
}

func contextAuthCases() []contextAuthCase {
	return []contextAuthCase{
		{name: "disabled empty target", environment: envDevelopment},
		{name: "disabled loopback without token", environment: envDevelopment, target: "127.0.0.1:9092"},
		{name: "disabled non-loopback is not dialled with a token", environment: envDevelopment, target: "10.1.2.3:9092"},
		{name: "enabled empty target needs no token", environment: envDevelopment, enabled: true},
		{
			name: "enabled loopback requires token", environment: envDevelopment, enabled: true,
			target: "127.0.0.1:9092", wantErr: "IBEX_CONTEXT_GRPC_SERVICE_TOKEN is required",
		},
		{
			name: "enabled loopback with token", environment: envDevelopment, enabled: true,
			target: "127.0.0.1:9092", token: testContextServiceToken,
		},
		{
			name: "enabled localhost hostname with token", environment: envDevelopment, enabled: true,
			target: "localhost:9092", token: testContextServiceToken,
		},
		{
			name: "enabled ipv6 loopback with token", environment: envDevelopment, enabled: true,
			target: "[::1]:9092", token: testContextServiceToken,
		},
		{
			name: "enabled rejects unspecified ipv4", environment: envDevelopment, enabled: true,
			target: "0.0.0.0:9092", token: testContextServiceToken, wantErr: "resolves to 0.0.0.0",
		},
		{
			name: "enabled rejects unspecified ipv6", environment: envDevelopment, enabled: true,
			target: "[::]:9092", token: testContextServiceToken, wantErr: "resolves to ::",
		},
		{
			name: "enabled rejects private remote ip", environment: envDevelopment, enabled: true,
			target: "10.1.2.3:9092", token: testContextServiceToken, wantErr: "resolves to 10.1.2.3",
		},
		{
			name: "enabled rejects unresolvable host", environment: envDevelopment, enabled: true,
			target: "context.invalid:9092", token: testContextServiceToken,
			wantErr: "must resolve to a loopback address",
		},
		{
			name: "enabled rejects a non-deployable test environment", environment: "test", enabled: true,
			target: "127.0.0.1:9092", token: testContextServiceToken, wantErr: "IBEX_ENV=test",
		},
		{
			name: "enabled rejects staging", environment: envStaging, enabled: true,
			target: "127.0.0.1:9092", token: testContextServiceToken, wantErr: "IBEX_ENV=staging",
		},
		{
			name: "enabled rejects production", environment: envProduction, enabled: true,
			target: "127.0.0.1:9092", token: testContextServiceToken, wantErr: "IBEX_ENV=production",
		},
		{
			name: "enabled rejects malformed target", environment: envDevelopment, enabled: true,
			target: "not-host-port", token: testContextServiceToken, wantErr: "must be host:port",
		},
	}
}

func TestUnit_ContextCallerAuthConfigMatrix(t *testing.T) {
	t.Parallel()
	for _, tc := range contextAuthCases() {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			cfg := contextAuthConfig(tc)
			err := cfg.validateContextGRPCConfig()
			if tc.wantErr == "" {
				if err != nil {
					t.Fatalf("validateContextGRPCConfig() error=%v, want accept", err)
				}
				return
			}
			if err == nil {
				t.Fatalf("validateContextGRPCConfig() error=nil, want rejection containing %q", tc.wantErr)
			}
			if !strings.Contains(err.Error(), tc.wantErr) {
				t.Fatalf("error=%v, want rejection containing %q", err, tc.wantErr)
			}
		})
	}
}

// TestUnit_ValidateContextEnvironment_NamesEnvAndReason pins the operator-facing
// message: it must name the environment and the missing-TLS reason.
func TestUnit_ValidateContextEnvironment_NamesEnvAndReason(t *testing.T) {
	t.Parallel()
	err := validateContextEnvironment(envStaging)
	if err == nil {
		t.Fatal("want error for staging")
	}
	for _, want := range []string{"IBEX_ENV=staging", "TLS"} {
		if !strings.Contains(err.Error(), want) {
			t.Fatalf("error=%v must contain %q", err, want)
		}
	}
}

func TestValidate_AcceptsEnabledContextInDevelopment(t *testing.T) {
	t.Parallel()
	cfg := validProxyConfig()
	cfg.ContextEnabled = true
	cfg.ContextGRPCServiceToken = testContextServiceToken
	if err := cfg.Validate(); err != nil {
		t.Fatalf("Validate() error=%v, want accept", err)
	}
}

func TestValidate_RejectsEnabledContextOutsideDevelopment(t *testing.T) {
	t.Parallel()
	for _, environment := range []string{envStaging, envProduction} {
		environment := environment
		t.Run(environment, func(t *testing.T) {
			t.Parallel()
			cfg := validProxyConfig()
			cfg.Environment = environment
			cfg.RedisURL = "redis://redis.internal:6379/0"
			cfg.ContextEnabled = true
			cfg.ContextGRPCServiceToken = testContextServiceToken
			err := cfg.Validate()
			if err == nil || !strings.Contains(err.Error(), "IBEX_CONTEXT_ENABLED=true is not supported") {
				t.Fatalf("Validate() error=%v, want context environment rejection", err)
			}
		})
	}
}
