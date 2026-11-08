package config

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

const testPostgresDSN = "postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable"

// setAuthBaseEnv pins a valid development config and clears the inline/file
// PEM pairs so an ambient shell value cannot decide the test outcome.
func setAuthBaseEnv(t *testing.T) {
	t.Helper()
	t.Setenv("IBEX_ENV", "development")
	t.Setenv("POSTGRES_DSN", testPostgresDSN)
	t.Setenv("IBEX_AUTH_TOTP_ENABLED", "false")
	t.Setenv("JWT_PRIVATE_KEY_PEM", "")
	t.Setenv("JWT_PRIVATE_KEY_FILE", "")
	t.Setenv("IBEX_AUTH_POLICY_SIGNING_KEY_PEM", "")
	t.Setenv("IBEX_AUTH_POLICY_SIGNING_KEY_FILE", "")
}

func writeTempPEM(t *testing.T, name, content string) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), name)
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
		t.Fatalf("write %s: %v", name, err)
	}
	return path
}

func TestLoad_PEMFileFallback(t *testing.T) {
	jwtPEM := "-----BEGIN " + "PRIVATE KEY-----\nJWT-MATERIAL\n" + "-----END " + "PRIVATE KEY-----"
	jwtPath := writeTempPEM(t, "jwt.pem", jwtPEM+"\n\n")
	policyPath := writeTempPEM(t, "policy.pem", policySigningPEM(t)+"\n")

	t.Run("jwt file loads", func(t *testing.T) {
		setAuthBaseEnv(t)
		t.Setenv("JWT_PRIVATE_KEY_FILE", jwtPath)

		cfg, err := Load()
		if err != nil {
			t.Fatalf("Load: %v", err)
		}
		if cfg.JWTPrivateKeyPEM != jwtPEM {
			t.Fatalf("JWTPrivateKeyPEM = %q, want trimmed file contents", cfg.JWTPrivateKeyPEM)
		}
	})

	t.Run("policy signing file loads", func(t *testing.T) {
		setAuthBaseEnv(t)
		t.Setenv("IBEX_AUTH_POLICY_SIGNING_KEY_FILE", policyPath)

		cfg, err := Load()
		if err != nil {
			t.Fatalf("Load: %v", err)
		}
		if cfg.PolicySigningKeyPEM != strings.TrimSpace(policySigningPEM(t)) {
			t.Fatal("PolicySigningKeyPEM was not loaded from IBEX_AUTH_POLICY_SIGNING_KEY_FILE")
		}
	})
}

func TestLoad_PEMInlineWinsOverFile(t *testing.T) {
	missing := filepath.Join(t.TempDir(), "missing.pem")

	t.Run("jwt", func(t *testing.T) {
		setAuthBaseEnv(t)
		t.Setenv("JWT_PRIVATE_KEY_PEM", "inline-jwt-wins")
		t.Setenv("JWT_PRIVATE_KEY_FILE", missing)

		cfg, err := Load()
		if err != nil {
			t.Fatalf("inline PEM must not read the file: %v", err)
		}
		if cfg.JWTPrivateKeyPEM != "inline-jwt-wins" {
			t.Fatalf("JWTPrivateKeyPEM = %q, want inline value", cfg.JWTPrivateKeyPEM)
		}
	})

	t.Run("policy signing", func(t *testing.T) {
		setAuthBaseEnv(t)
		inline := policySigningPEM(t)
		t.Setenv("IBEX_AUTH_POLICY_SIGNING_KEY_PEM", inline)
		t.Setenv("IBEX_AUTH_POLICY_SIGNING_KEY_FILE", missing)

		cfg, err := Load()
		if err != nil {
			t.Fatalf("inline PEM must not read the file: %v", err)
		}
		if cfg.PolicySigningKeyPEM != strings.TrimSpace(inline) {
			t.Fatal("PolicySigningKeyPEM did not keep the inline value")
		}
	})
}

func TestLoad_PEMFileFailuresNameEnv(t *testing.T) {
	missing := filepath.Join(t.TempDir(), "missing.pem")
	empty := writeTempPEM(t, "empty.pem", " \n\t")
	cases := []struct {
		name   string
		envVar string
		path   string
	}{
		{name: "jwt missing", envVar: "JWT_PRIVATE_KEY_FILE", path: missing},
		{name: "policy missing", envVar: "IBEX_AUTH_POLICY_SIGNING_KEY_FILE", path: missing},
		{name: "jwt empty", envVar: "JWT_PRIVATE_KEY_FILE", path: empty},
		{name: "policy empty", envVar: "IBEX_AUTH_POLICY_SIGNING_KEY_FILE", path: empty},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			setAuthBaseEnv(t)
			t.Setenv(tc.envVar, tc.path)

			_, err := Load()
			if err == nil || !strings.Contains(err.Error(), tc.envVar) {
				t.Fatalf("Load() error = %v, want error naming %s", err, tc.envVar)
			}
		})
	}
}

func TestLoad_DevelopmentWithoutPEMFiles(t *testing.T) {
	setAuthBaseEnv(t)

	cfg, err := Load()
	if err != nil {
		t.Fatalf("development without PEM material: %v", err)
	}
	if cfg.JWTPrivateKeyPEM != "" || cfg.PolicySigningKeyPEM != "" {
		t.Fatalf("PEM fields must stay empty: jwt=%q policy=%q", cfg.JWTPrivateKeyPEM, cfg.PolicySigningKeyPEM)
	}
}
