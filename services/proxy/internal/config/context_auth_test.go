package config

import (
	"strings"
	"testing"
)

// testContextServiceToken is a stand-in for IBEX_CONTEXT_GRPC_SERVICE_TOKEN.
// Built at runtime so the fixture is never mistaken for a committed credential.
var testContextServiceToken = strings.Repeat("0123456789abcdef", 2)

// contextTokenShapeErr is the operator-facing rejection for a token the context
// server would refuse (ADR-0096: 32-512 characters from [A-Za-z0-9_-]).
const contextTokenShapeErr = "must be 32-512 characters from [A-Za-z0-9_-]"

// contextColocationErr is the ADR-0097 §4 rejection for enabling plaintext
// context outside development without declaring co-location.
const contextColocationErr = "IBEX_CONTEXT_COLOCATED"

// contextAuthCase is one row of the ADR-0096 caller-auth / ADR-0097 §4
// co-location config matrix.
type contextAuthCase struct {
	name        string
	environment string
	enabled     bool
	colocated   bool
	target      string
	token       string
	wantErr     string // substring; empty means the config must validate
}

func contextAuthConfig(tc contextAuthCase) Config {
	return Config{
		Environment:             tc.environment,
		ContextEnabled:          tc.enabled,
		ContextColocated:        tc.colocated,
		ContextGRPCTarget:       tc.target,
		ContextGRPCServiceToken: tc.token,
		ContextAssembleTimeout:  defaultContextAssembleTimeout,
	}
}

// contextAuthCases is the full ADR-0096 caller-auth config matrix.
func contextAuthCases() []contextAuthCase {
	cases := contextActivationCases()
	cases = append(cases, contextTokenShapeCases()...)
	cases = append(cases, contextTargetCases()...)
	return append(cases, contextEnvironmentCases()...)
}

// contextActivationCases covers the flag/target combinations: which of them
// dial at all, and which of those require a token.
func contextActivationCases() []contextAuthCase {
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
	}
}

// contextTokenShapeCases pins the wire shape shared with the context server:
// 32-512 characters from [A-Za-z0-9_-].
func contextTokenShapeCases() []contextAuthCase {
	return []contextAuthCase{
		{
			// The server pattern is ^[A-Za-z0-9_-]{32,512}$; a token outside it
			// makes gRPC-Go reject the metadata as Internal, so startup must fail
			// here rather than proceed with a token that can never authenticate.
			name: "enabled rejects a 31-character token", environment: envDevelopment, enabled: true,
			target: "127.0.0.1:9092", token: strings.Repeat("a", 31), wantErr: contextTokenShapeErr,
		},
		{
			name: "enabled accepts a 32-character token", environment: envDevelopment, enabled: true,
			target: "127.0.0.1:9092", token: strings.Repeat("a", 32),
		},
		{
			name: "enabled accepts a 512-character token", environment: envDevelopment, enabled: true,
			target: "127.0.0.1:9092", token: strings.Repeat("a", 512),
		},
		{
			name: "enabled rejects a 513-character token", environment: envDevelopment, enabled: true,
			target: "127.0.0.1:9092", token: strings.Repeat("a", 513), wantErr: contextTokenShapeErr,
		},
		{
			name: "enabled rejects a trailing newline", environment: envDevelopment, enabled: true,
			target: "127.0.0.1:9092", token: testContextServiceToken + "\n", wantErr: contextTokenShapeErr,
		},
		{
			name: "enabled rejects a non-ASCII token", environment: envDevelopment, enabled: true,
			target: "127.0.0.1:9092", token: strings.Repeat("a", 31) + "é", wantErr: contextTokenShapeErr,
		},
		{
			name: "enabled rejects a token with a space", environment: envDevelopment, enabled: true,
			target: "127.0.0.1:9092", token: strings.Repeat("a", 31) + " ", wantErr: contextTokenShapeErr,
		},
		{
			name: "enabled accepts hyphen and underscore", environment: envDevelopment, enabled: true,
			target: "127.0.0.1:9092", token: "ABCDEFGHIJ_KLMNOPQRST-UVWXYZ012345",
		},
	}
}

// contextTargetCases covers host:port parsing and the loopback-only rule that
// keeps the cleartext token off the network.
func contextTargetCases() []contextAuthCase {
	return []contextAuthCase{
		{
			name: "enabled rejects a localhost hostname", environment: envDevelopment, enabled: true,
			target: "localhost:9092", token: testContextServiceToken, wantErr: "loopback IP literal",
		},
		{
			name: "enabled ipv6 loopback with token", environment: envDevelopment, enabled: true,
			target: "[::1]:9092", token: testContextServiceToken,
		},
		{
			name: "enabled rejects unspecified ipv4", environment: envDevelopment, enabled: true,
			target: "0.0.0.0:9092", token: testContextServiceToken, wantErr: "is 0.0.0.0",
		},
		{
			name: "enabled rejects unspecified ipv6", environment: envDevelopment, enabled: true,
			target: "[::]:9092", token: testContextServiceToken, wantErr: "is ::",
		},
		{
			name: "enabled rejects private remote ip", environment: envDevelopment, enabled: true,
			target: "10.1.2.3:9092", token: testContextServiceToken, wantErr: "is 10.1.2.3",
		},
		{
			name: "enabled rejects a hostname", environment: envDevelopment, enabled: true,
			target: "context.invalid:9092", token: testContextServiceToken,
			wantErr: "loopback IP literal",
		},
		{
			name: "enabled rejects malformed target", environment: envDevelopment, enabled: true,
			target: "not-host-port", token: testContextServiceToken, wantErr: "must be host:port",
		},
		{
			name: "enabled rejects a padded target", environment: envDevelopment, enabled: true,
			target: " 127.0.0.1:9092 ", token: testContextServiceToken, wantErr: "leading or trailing whitespace",
		},
	}
}

// contextEnvironmentCases covers the ADR-0097 §4 plaintext boundary: development
// may dial plaintext; every other profile needs the explicit co-location opt-in,
// and the opt-in never relaxes the loopback-target rule.
func contextEnvironmentCases() []contextAuthCase {
	return []contextAuthCase{
		{
			name: "enabled rejects a non-deployable test environment", environment: "test", enabled: true,
			target: "127.0.0.1:9092", token: testContextServiceToken, wantErr: "IBEX_ENV=test",
		},
		{
			name: "staging without co-location opt-in is rejected", environment: envStaging, enabled: true,
			target: "127.0.0.1:9092", token: testContextServiceToken, wantErr: contextColocationErr,
		},
		{
			name: "production without co-location opt-in is rejected", environment: envProduction, enabled: true,
			target: "127.0.0.1:9092", token: testContextServiceToken, wantErr: contextColocationErr,
		},
		{
			name: "production with co-location opt-in on loopback validates", environment: envProduction, enabled: true,
			colocated: true, target: "127.0.0.1:9092", token: testContextServiceToken,
		},
		{
			// The opt-in is not a bypass: a non-loopback target still carries the
			// cleartext service token off the host, so isolation wins.
			name: "production co-location opt-in cannot bypass loopback isolation", environment: envProduction, enabled: true,
			colocated: true, target: "10.1.2.3:9092", token: testContextServiceToken, wantErr: "is 10.1.2.3",
		},
		{
			// Loopback is checked before the environment rule, so a missing opt-in
			// never turns a non-loopback target into an environment-only error.
			name: "production without opt-in on a non-loopback target is still a loopback rejection", environment: envProduction, enabled: true,
			target: "10.1.2.3:9092", token: testContextServiceToken, wantErr: "is 10.1.2.3",
		},
		{
			name: "development without co-location opt-in still validates", environment: envDevelopment, enabled: true,
			target: "127.0.0.1:9092", token: testContextServiceToken,
		},
		{
			// The gate only applies when context can run; a disabled client never
			// carries the token, so it needs no opt-in.
			name: "disabled context outside development needs no opt-in", environment: envProduction, enabled: false,
			target: "127.0.0.1:9092", token: testContextServiceToken,
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

// TestUnit_ValidateContextServiceToken_NamesVarShapeAndHidesValue pins the
// operator-facing message for a malformed token: it must name the variable and
// the allowed shape, and must never print the secret.
func TestUnit_ValidateContextServiceToken_NamesVarShapeAndHidesValue(t *testing.T) {
	t.Parallel()

	const secret = "super-secret-token-value-that-must-not-leak"
	err := validateContextServiceToken(secret + "\n")
	if err == nil {
		t.Fatal("want rejection for a token with a trailing newline")
	}
	msg := err.Error()
	for _, want := range []string{"IBEX_CONTEXT_GRPC_SERVICE_TOKEN", "[A-Za-z0-9_-]", "32-512"} {
		if !strings.Contains(msg, want) {
			t.Fatalf("error=%q must contain %q", msg, want)
		}
	}
	if strings.Contains(msg, secret) {
		t.Fatalf("error=%q must never echo the token value", msg)
	}
	if err := validateContextServiceToken(testContextServiceToken); err != nil {
		t.Fatalf("validateContextServiceToken(valid) error=%v, want accept", err)
	}
}

// TestUnit_ValidateContextEnvironment_NamesVarAndBoundary pins the operator-facing
// ADR-0097 §4 message: it must name the environment and the missing co-location
// opt-in, and state the plaintext boundary it stands for.
func TestUnit_ValidateContextEnvironment_NamesVarAndBoundary(t *testing.T) {
	t.Parallel()
	err := validateContextEnvironment(envStaging, false)
	if err == nil {
		t.Fatal("want error for staging without the co-location opt-in")
	}
	for _, want := range []string{"IBEX_ENV=staging", "IBEX_CONTEXT_COLOCATED", "network namespace", "loopback"} {
		if !strings.Contains(err.Error(), want) {
			t.Fatalf("error=%v must contain %q", err, want)
		}
	}
	if err := validateContextEnvironment(envStaging, true); err != nil {
		t.Fatalf("co-located staging error=%v, want accept", err)
	}
	if err := validateContextEnvironment(envDevelopment, false); err != nil {
		t.Fatalf("development error=%v, want accept", err)
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

func TestValidate_RejectsEnabledContextOutsideDevelopmentWithoutColocation(t *testing.T) {
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
			if err == nil || !strings.Contains(err.Error(), contextColocationErr) {
				t.Fatalf("Validate() error=%v, want rejection naming %s", err, contextColocationErr)
			}
		})
	}
}

// TestValidate_AcceptsColocatedContextOutsideDevelopment pins the profile the
// ADR-0097 §4 opt-in exists for: production, loopback literal, explicit
// co-location, valid token.
func TestValidate_AcceptsColocatedContextOutsideDevelopment(t *testing.T) {
	t.Parallel()
	cfg := validProxyConfig()
	cfg.Environment = envProduction
	cfg.RedisURL = "redis://redis.internal:6379/0"
	cfg.ContextEnabled = true
	cfg.ContextColocated = true
	cfg.ContextGRPCServiceToken = testContextServiceToken
	cfg.LLMMode = envLLMModeLive
	cfg.OpenAI.APIKey = "sk-test-not-a-real-credential"
	if err := cfg.Validate(); err != nil {
		t.Fatalf("Validate() error=%v, want accept", err)
	}
}
