package config

import (
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/json"
	"encoding/pem"
	"strings"
	"sync"
	"testing"
)

var (
	proxyPolicyKeyOnce sync.Once
	proxyPolicyKeyJSON string
	proxyPolicyKeyErr  error
)

func proxyPolicyKeysJSON(t *testing.T) string {
	t.Helper()
	proxyPolicyKeyOnce.Do(func() {
		key, err := rsa.GenerateKey(rand.Reader, 2048)
		if err != nil {
			proxyPolicyKeyErr = err
			return
		}
		der, err := x509.MarshalPKIXPublicKey(&key.PublicKey)
		if err != nil {
			proxyPolicyKeyErr = err
			return
		}
		pemStr := string(pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: der}))
		raw, err := json.Marshal(map[string]string{"v1": pemStr})
		if err != nil {
			proxyPolicyKeyErr = err
			return
		}
		proxyPolicyKeyJSON = string(raw)
	})
	if proxyPolicyKeyErr != nil {
		t.Fatal(proxyPolicyKeyErr)
	}
	return proxyPolicyKeyJSON
}

func TestValidate_PolicySnapshotConfig(t *testing.T) {
	t.Parallel()

	t.Run("empty keys accepted", func(t *testing.T) {
		t.Parallel()
		cfg := validProxyConfig()
		if err := cfg.Validate(); err != nil {
			t.Fatalf("empty policy keys: %v", err)
		}
	})

	t.Run("valid key set accepted", func(t *testing.T) {
		t.Parallel()
		cfg := validProxyConfig()
		cfg.PolicyPublicKeysJSON = "  " + proxyPolicyKeysJSON(t) + "  "
		cfg.PolicyMinEpoch = 2
		if err := cfg.Validate(); err != nil {
			t.Fatalf("valid policy keys: %v", err)
		}
	})

	t.Run("invalid json rejected", func(t *testing.T) {
		t.Parallel()
		cfg := validProxyConfig()
		cfg.PolicyPublicKeysJSON = "{not-json"
		err := cfg.Validate()
		if err == nil || !strings.Contains(err.Error(), "IBEX_PROXY_POLICY_PUBLIC_KEYS") {
			t.Fatalf("invalid policy keys err = %v", err)
		}
	})

	t.Run("garbage pem rejected", func(t *testing.T) {
		t.Parallel()
		cfg := validProxyConfig()
		cfg.PolicyPublicKeysJSON = `{"v1":"not-a-pem"}`
		if err := cfg.Validate(); err == nil {
			t.Fatal("expected garbage pem error")
		}
	})

	t.Run("negative min epoch rejected", func(t *testing.T) {
		t.Parallel()
		cfg := validProxyConfig()
		cfg.PolicyMinEpoch = -1
		err := cfg.Validate()
		if err == nil || !strings.Contains(err.Error(), "IBEX_PROXY_POLICY_MIN_EPOCH") {
			t.Fatalf("negative min epoch err = %v", err)
		}
	})
}
