package config

import (
	"strings"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/infra/testing/tlscert"
)

// nonDevelopmentAuthConfig satisfies every non-development requirement except
// the gRPC TLS pair, so a TLS assertion is not masked by an earlier validation.
func nonDevelopmentAuthConfig(t *testing.T, environment string) Config {
	t.Helper()
	cfg := validAuthConfig()
	cfg.Environment = environment
	cfg.CredentialsMasterKey = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
	cfg.PolicySigningKeyPEM = policySigningPEM(t)
	return cfg
}

// TestValidate_GRPCTLS_DevelopmentWithoutPairAllowed pins the one profile that
// may serve the plaintext listener (ADR-0097 §4).
func TestValidate_GRPCTLS_DevelopmentWithoutPairAllowed(t *testing.T) {
	t.Parallel()
	cfg := validAuthConfig()
	if err := cfg.Validate(); err != nil {
		t.Fatalf("development without pair: %v", err)
	}
}

func TestValidate_GRPCTLS_NonDevelopmentRequiresPair(t *testing.T) {
	t.Parallel()
	for _, environment := range []string{"staging", "production"} {
		environment := environment
		t.Run(environment+" without pair is rejected", func(t *testing.T) {
			t.Parallel()
			cfg := nonDevelopmentAuthConfig(t, environment)
			err := cfg.Validate()
			if err == nil {
				t.Fatal("expected missing gRPC TLS pair error")
			}
			assertNamesEnv(t, err, "IBEX_AUTH_GRPC_TLS_CERT_FILE")
			assertNamesEnv(t, err, "IBEX_AUTH_GRPC_TLS_KEY_FILE")
		})
	}
}

func TestValidate_GRPCTLS_PartialPairRejected(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name    string
		setCert bool
		wantEnv string
	}{
		{name: "cert without key", setCert: true, wantEnv: "IBEX_AUTH_GRPC_TLS_KEY_FILE"},
		{name: "key without cert", setCert: false, wantEnv: "IBEX_AUTH_GRPC_TLS_CERT_FILE"},
	}
	for _, tc := range cases {
		tc := tc
		t.Run(tc.name+" is rejected", func(t *testing.T) {
			t.Parallel()
			cfg := validAuthConfig()
			pair := tlscert.Generate(t, t.TempDir(), tlscert.Options{})
			if tc.setCert {
				cfg.GRPCTLSCertFile = pair.CertFile
			} else {
				cfg.GRPCTLSKeyFile = pair.KeyFile
			}
			err := cfg.Validate()
			if err == nil {
				t.Fatal("expected one-of-two gRPC TLS error")
			}
			assertNamesEnv(t, err, tc.wantEnv)
		})
	}
}

func TestValidate_GRPCTLS_ValidPairAccepted(t *testing.T) {
	t.Parallel()
	cfg := nonDevelopmentAuthConfig(t, "staging")
	pair := tlscert.Generate(t, t.TempDir(), tlscert.Options{})
	cfg.GRPCTLSCertFile = pair.CertFile
	cfg.GRPCTLSKeyFile = pair.KeyFile
	if err := cfg.Validate(); err != nil {
		t.Fatalf("valid gRPC TLS pair: %v", err)
	}
}

func TestValidate_GRPCTLS_MismatchedPairRejected(t *testing.T) {
	t.Parallel()
	cfg := validAuthConfig()
	certPair := tlscert.Generate(t, t.TempDir(), tlscert.Options{})
	keyPair := tlscert.Generate(t, t.TempDir(), tlscert.Options{})
	cfg.GRPCTLSCertFile = certPair.CertFile
	cfg.GRPCTLSKeyFile = keyPair.KeyFile
	if err := cfg.Validate(); err == nil {
		t.Fatal("expected mismatched gRPC TLS pair error")
	}
}

func TestValidate_GRPCTLS_InvalidLeafRejected(t *testing.T) {
	t.Parallel()
	now := time.Now()
	cases := []struct {
		name string
		opts tlscert.Options
	}{
		{
			name: "expired leaf",
			opts: tlscert.Options{NotBefore: now.Add(-48 * time.Hour), NotAfter: now.Add(-24 * time.Hour)},
		},
		{
			name: "not-yet-valid leaf",
			opts: tlscert.Options{NotBefore: now.Add(24 * time.Hour), NotAfter: now.Add(48 * time.Hour)},
		},
		{name: "leaf without SAN", opts: tlscert.Options{NoSAN: true}},
	}
	for _, tc := range cases {
		tc := tc
		t.Run(tc.name+" is rejected", func(t *testing.T) {
			t.Parallel()
			cfg := validAuthConfig()
			pair := tlscert.Generate(t, t.TempDir(), tc.opts)
			cfg.GRPCTLSCertFile = pair.CertFile
			cfg.GRPCTLSKeyFile = pair.KeyFile
			err := cfg.Validate()
			if err == nil {
				t.Fatal("expected invalid gRPC TLS leaf error")
			}
			assertNamesEnv(t, err, "IBEX_AUTH_GRPC_TLS_CERT_FILE")
		})
	}
}

func TestLoad_GRPCTLSFiles(t *testing.T) {
	pair := tlscert.Generate(t, t.TempDir(), tlscert.Options{})
	t.Setenv("IBEX_ENV", "development")
	t.Setenv("POSTGRES_DSN", "postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable")
	t.Setenv("IBEX_AUTH_GRPC_TLS_CERT_FILE", pair.CertFile)
	t.Setenv("IBEX_AUTH_GRPC_TLS_KEY_FILE", pair.KeyFile)

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if cfg.GRPCTLSCertFile != pair.CertFile || cfg.GRPCTLSKeyFile != pair.KeyFile {
		t.Fatalf("grpc tls paths = %q/%q, want %q/%q",
			cfg.GRPCTLSCertFile, cfg.GRPCTLSKeyFile, pair.CertFile, pair.KeyFile)
	}
}

func assertNamesEnv(t *testing.T, err error, name string) {
	t.Helper()
	if !strings.Contains(err.Error(), name) {
		t.Fatalf("error %q does not name %s", err.Error(), name)
	}
}
