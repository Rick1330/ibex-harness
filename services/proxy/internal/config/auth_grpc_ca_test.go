package config

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/infra/testing/tlscert"
)

// TestValidate_AuthGRPCCACert pins the ADR-0097 §4 client CA rule: empty is
// allowed, a readable bundle with at least one certificate is accepted, and
// every unusable path fails startup with an error naming the variable.
func TestValidate_AuthGRPCCACert(t *testing.T) {
	t.Parallel()

	pair := tlscert.Generate(t, t.TempDir(), tlscert.Options{})
	garbage := filepath.Join(t.TempDir(), "garbage.pem")
	if err := os.WriteFile(garbage, []byte("not a pem certificate"), 0o644); err != nil {
		t.Fatalf("write garbage: %v", err)
	}

	tests := []struct {
		name    string
		caFile  string
		wantErr bool
	}{
		{name: "empty is allowed", caFile: ""},
		{name: "valid bundle is accepted", caFile: pair.CAFile},
		{name: "missing file is rejected", caFile: filepath.Join(t.TempDir(), "missing.pem"), wantErr: true},
		{name: "directory path is rejected", caFile: t.TempDir(), wantErr: true},
		{name: "garbage bundle is rejected", caFile: garbage, wantErr: true},
	}
	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			cfg := validProxyConfig()
			cfg.AuthGRPCCACertFile = tc.caFile
			err := cfg.Validate()
			if tc.wantErr {
				if err == nil {
					t.Fatal("expected validation error")
				}
				if !strings.Contains(err.Error(), "IBEX_AUTH_GRPC_CA_FILE") {
					t.Fatalf("error %q does not name IBEX_AUTH_GRPC_CA_FILE", err.Error())
				}
				return
			}
			if err != nil {
				t.Fatalf("Validate: %v", err)
			}
		})
	}
}

func TestLoad_AuthGRPCCACertFile(t *testing.T) {
	pair := tlscert.Generate(t, t.TempDir(), tlscert.Options{})
	withProxyEnv(t, map[string]string{
		"IBEX_ENV":               "development",
		"IBEX_AUTH_GRPC_CA_FILE": pair.CAFile,
	})
	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if cfg.AuthGRPCCACertFile != pair.CAFile {
		t.Fatalf("AuthGRPCCACertFile = %q, want %q", cfg.AuthGRPCCACertFile, pair.CAFile)
	}
}

// TestValidate_ProductionColocatedContextWithAuthCA is the cross-slice config
// gate: the production co-located context opt-in, its loopback target and
// caller token, and the AuthService CA bundle must all validate in one Config.
// A regression in any slice that only composes correctly in isolation fails
// here. The CA comes from the shared test-cert helper and is written under
// t.TempDir().
func TestValidate_ProductionColocatedContextWithAuthCA(t *testing.T) {
	t.Parallel()

	pair := tlscert.Generate(t, t.TempDir(), tlscert.Options{})
	cfg := validProxyConfig()
	cfg.Environment = envProduction
	cfg.RedisURL = "redis://redis.internal:6379/0"
	cfg.ContextEnabled = true
	cfg.ContextColocated = true
	cfg.ContextGRPCTarget = "127.0.0.1:9092"
	cfg.ContextGRPCServiceToken = testContextServiceToken
	cfg.AuthGRPCCACertFile = pair.CAFile
	cfg.LLMMode = envLLMModeLive
	cfg.OpenAI.APIKey = "sk-test-not-a-real-credential"

	if err := cfg.Validate(); err != nil {
		t.Fatalf("Validate() error=%v, want accept", err)
	}
}
