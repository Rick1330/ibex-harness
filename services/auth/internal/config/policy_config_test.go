package config

import (
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/pem"
	"strings"
	"sync"
	"testing"
)

var (
	testPolicyPEMOnce sync.Once
	testPolicyPEM     string
	testPolicyPEMErr  error
)

func policySigningPEM(t *testing.T) string {
	t.Helper()
	testPolicyPEMOnce.Do(func() {
		key, err := rsa.GenerateKey(rand.Reader, 2048)
		if err != nil {
			testPolicyPEMErr = err
			return
		}
		testPolicyPEM = string(pem.EncodeToMemory(&pem.Block{
			Type: "RSA PRIVATE KEY", Bytes: x509.MarshalPKCS1PrivateKey(key),
		}))
	})
	if testPolicyPEMErr != nil {
		t.Fatal(testPolicyPEMErr)
	}
	return testPolicyPEM
}

func TestValidate_PolicySigningConfig(t *testing.T) {
	t.Parallel()

	t.Run("development without key allowed", func(t *testing.T) {
		t.Parallel()
		cfg := validAuthConfig()
		if err := cfg.Validate(); err != nil {
			t.Fatalf("development without signing key: %v", err)
		}
	})

	t.Run("staging requires key", func(t *testing.T) {
		t.Parallel()
		cfg := validAuthConfig()
		cfg.Environment = "staging"
		err := cfg.Validate()
		if err == nil || !strings.Contains(err.Error(), "IBEX_AUTH_POLICY_SIGNING_KEY_PEM") {
			t.Fatalf("staging without signing key err = %v", err)
		}
	})

	t.Run("invalid key rejected", func(t *testing.T) {
		t.Parallel()
		cfg := validAuthConfig()
		cfg.PolicySigningKeyPEM = "not-a-pem"
		if err := cfg.Validate(); err == nil {
			t.Fatal("expected invalid signing key error")
		}
	})

	t.Run("valid key accepted", func(t *testing.T) {
		t.Parallel()
		cfg := validAuthConfig()
		cfg.Environment = "staging"
		cfg.PolicySigningKeyPEM = policySigningPEM(t)
		cfg.PolicyEpoch = 3
		cfg.PolicySigningKeyID = "v2"
		if err := cfg.Validate(); err != nil {
			t.Fatalf("valid signing key: %v", err)
		}
	})

	t.Run("zero epoch defaults to one", func(t *testing.T) {
		t.Parallel()
		cfg := validAuthConfig()
		cfg.PolicySigningKeyPEM = policySigningPEM(t)
		cfg.PolicyEpoch = 0
		if err := cfg.Validate(); err != nil {
			t.Fatalf("zero epoch should default: %v", err)
		}
		if got := cfg.PolicyIssuerConfig().Epoch; got != 1 {
			t.Fatalf("defaulted epoch = %d, want 1", got)
		}
	})

	t.Run("negative epoch rejected", func(t *testing.T) {
		t.Parallel()
		cfg := validAuthConfig()
		cfg.PolicySigningKeyPEM = policySigningPEM(t)
		cfg.PolicyEpoch = -1
		if err := cfg.Validate(); err == nil {
			t.Fatal("expected negative epoch error")
		}
	})
}
