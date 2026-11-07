package config

import (
	"strings"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/infra/testing/tlscert"
)

// TestValidate_GRPCTLS pins the ADR-0097 §4 AuthService server TLS rule:
// development may serve plaintext, every other profile must present a valid
// certificate pair, and a configured pair is always validated.
func TestValidate_GRPCTLS(t *testing.T) {
	t.Parallel()

	t.Run("development without pair is allowed", func(t *testing.T) {
		t.Parallel()
		cfg := validAuthConfig()
		if err := cfg.Validate(); err != nil {
			t.Fatalf("development without pair: %v", err)
		}
	})

	for _, environment := range []string{"staging", "production"} {
		environment := environment
		t.Run(environment+" without pair is rejected", func(t *testing.T) {
			t.Parallel()
			cfg := validAuthConfig()
			cfg.Environment = environment
			// Satisfy the other non-development requirements so the assertion
			// is about the missing gRPC TLS pair, not an earlier validation.
			cfg.CredentialsMasterKey = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
			cfg.PolicySigningKeyPEM = policySigningPEM(t)
			err := cfg.Validate()
			if err == nil {
				t.Fatal("expected missing gRPC TLS pair error")
			}
			assertNamesEnv(t, err, "IBEX_AUTH_GRPC_TLS_CERT_FILE")
			assertNamesEnv(t, err, "IBEX_AUTH_GRPC_TLS_KEY_FILE")
		})
	}

	t.Run("cert without key is rejected", func(t *testing.T) {
		t.Parallel()
		cfg := validAuthConfig()
		pair := tlscert.Generate(t, t.TempDir(), tlscert.Options{})
		cfg.GRPCTLSCertFile = pair.CertFile
		err := cfg.Validate()
		if err == nil {
			t.Fatal("expected one-of-two gRPC TLS error")
		}
		assertNamesEnv(t, err, "IBEX_AUTH_GRPC_TLS_KEY_FILE")
	})

	t.Run("key without cert is rejected", func(t *testing.T) {
		t.Parallel()
		cfg := validAuthConfig()
		pair := tlscert.Generate(t, t.TempDir(), tlscert.Options{})
		cfg.GRPCTLSKeyFile = pair.KeyFile
		err := cfg.Validate()
		if err == nil {
			t.Fatal("expected one-of-two gRPC TLS error")
		}
		assertNamesEnv(t, err, "IBEX_AUTH_GRPC_TLS_CERT_FILE")
	})

	t.Run("valid pair is accepted outside development", func(t *testing.T) {
		t.Parallel()
		cfg := validAuthConfig()
		cfg.Environment = "staging"
		cfg.PolicySigningKeyPEM = policySigningPEM(t)
		pair := tlscert.Generate(t, t.TempDir(), tlscert.Options{})
		cfg.GRPCTLSCertFile = pair.CertFile
		cfg.GRPCTLSKeyFile = pair.KeyFile
		if err := cfg.Validate(); err != nil {
			t.Fatalf("valid gRPC TLS pair: %v", err)
		}
	})

	t.Run("mismatched pair is rejected", func(t *testing.T) {
		t.Parallel()
		cfg := validAuthConfig()
		certPair := tlscert.Generate(t, t.TempDir(), tlscert.Options{})
		keyPair := tlscert.Generate(t, t.TempDir(), tlscert.Options{})
		cfg.GRPCTLSCertFile = certPair.CertFile
		cfg.GRPCTLSKeyFile = keyPair.KeyFile
		if err := cfg.Validate(); err == nil {
			t.Fatal("expected mismatched gRPC TLS pair error")
		}
	})

	t.Run("expired leaf is rejected", func(t *testing.T) {
		t.Parallel()
		cfg := validAuthConfig()
		now := time.Now()
		pair := tlscert.Generate(t, t.TempDir(), tlscert.Options{
			NotBefore: now.Add(-48 * time.Hour),
			NotAfter:  now.Add(-24 * time.Hour),
		})
		cfg.GRPCTLSCertFile = pair.CertFile
		cfg.GRPCTLSKeyFile = pair.KeyFile
		err := cfg.Validate()
		if err == nil {
			t.Fatal("expected expired gRPC TLS leaf error")
		}
		assertNamesEnv(t, err, "IBEX_AUTH_GRPC_TLS_CERT_FILE")
	})

	t.Run("not-yet-valid leaf is rejected", func(t *testing.T) {
		t.Parallel()
		cfg := validAuthConfig()
		now := time.Now()
		pair := tlscert.Generate(t, t.TempDir(), tlscert.Options{
			NotBefore: now.Add(24 * time.Hour),
			NotAfter:  now.Add(48 * time.Hour),
		})
		cfg.GRPCTLSCertFile = pair.CertFile
		cfg.GRPCTLSKeyFile = pair.KeyFile
		err := cfg.Validate()
		if err == nil {
			t.Fatal("expected not-yet-valid gRPC TLS leaf error")
		}
		assertNamesEnv(t, err, "IBEX_AUTH_GRPC_TLS_CERT_FILE")
	})

	t.Run("leaf without SAN is rejected", func(t *testing.T) {
		t.Parallel()
		cfg := validAuthConfig()
		pair := tlscert.Generate(t, t.TempDir(), tlscert.Options{NoSAN: true})
		cfg.GRPCTLSCertFile = pair.CertFile
		cfg.GRPCTLSKeyFile = pair.KeyFile
		err := cfg.Validate()
		if err == nil {
			t.Fatal("expected no-SAN gRPC TLS leaf error")
		}
		assertNamesEnv(t, err, "IBEX_AUTH_GRPC_TLS_CERT_FILE")
	})
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
