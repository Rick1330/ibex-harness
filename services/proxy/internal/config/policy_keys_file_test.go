package config

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func setProxyPolicyKeysEnv(t *testing.T) {
	t.Helper()
	withProxyEnv(t, map[string]string{"IBEX_ENV": "development", "IBEX_LLM_MODE": "mock"})
	t.Setenv("IBEX_PROXY_POLICY_PUBLIC_KEYS", "")
	t.Setenv("IBEX_PROXY_POLICY_PUBLIC_KEYS_FILE", "")
}

func writeProxyPolicyKeysFile(t *testing.T, content string) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "policy-keys.json")
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
		t.Fatalf("write policy keys file: %v", err)
	}
	return path
}

func TestLoad_PolicyPublicKeysFile(t *testing.T) {
	keys := proxyPolicyKeysJSON(t)
	path := writeProxyPolicyKeysFile(t, "  "+keys+"\n")

	setProxyPolicyKeysEnv(t)
	t.Setenv("IBEX_PROXY_POLICY_PUBLIC_KEYS_FILE", path)

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if cfg.PolicyPublicKeysJSON != keys {
		t.Fatalf("PolicyPublicKeysJSON = %q, want trimmed file contents", cfg.PolicyPublicKeysJSON)
	}
}

func TestLoad_PolicyPublicKeysInlineWinsOverFile(t *testing.T) {
	keys := proxyPolicyKeysJSON(t)
	missing := filepath.Join(t.TempDir(), "missing.json")

	setProxyPolicyKeysEnv(t)
	t.Setenv("IBEX_PROXY_POLICY_PUBLIC_KEYS", keys)
	t.Setenv("IBEX_PROXY_POLICY_PUBLIC_KEYS_FILE", missing)

	cfg, err := Load()
	if err != nil {
		t.Fatalf("inline keys must not read the file: %v", err)
	}
	if cfg.PolicyPublicKeysJSON != keys {
		t.Fatal("inline policy keys did not win over the file")
	}
}

func TestLoad_PolicyPublicKeysFileMissingFails(t *testing.T) {
	missing := filepath.Join(t.TempDir(), "missing.json")

	setProxyPolicyKeysEnv(t)
	t.Setenv("IBEX_PROXY_POLICY_PUBLIC_KEYS_FILE", missing)

	_, err := Load()
	if err == nil || !strings.Contains(err.Error(), "IBEX_PROXY_POLICY_PUBLIC_KEYS_FILE") {
		t.Fatalf("Load() error = %v, want error naming IBEX_PROXY_POLICY_PUBLIC_KEYS_FILE", err)
	}
}

func TestLoad_PolicyPublicKeysFileEmptyFails(t *testing.T) {
	path := writeProxyPolicyKeysFile(t, " \n\t")

	setProxyPolicyKeysEnv(t)
	t.Setenv("IBEX_PROXY_POLICY_PUBLIC_KEYS_FILE", path)

	_, err := Load()
	if err == nil || !strings.Contains(err.Error(), "IBEX_PROXY_POLICY_PUBLIC_KEYS_FILE") {
		t.Fatalf("Load() error = %v, want error naming IBEX_PROXY_POLICY_PUBLIC_KEYS_FILE", err)
	}
}

func TestLoad_PolicyPublicKeysFileInvalidJSONFails(t *testing.T) {
	path := writeProxyPolicyKeysFile(t, "{not-json")

	setProxyPolicyKeysEnv(t)
	t.Setenv("IBEX_PROXY_POLICY_PUBLIC_KEYS_FILE", path)

	_, err := Load()
	if err == nil || !strings.Contains(err.Error(), "IBEX_PROXY_POLICY_PUBLIC_KEYS") {
		t.Fatalf("Load() error = %v, want existing JSON validation error", err)
	}
}

func TestLoad_PolicyPublicKeysEmptyStillAllowed(t *testing.T) {
	setProxyPolicyKeysEnv(t)

	cfg, err := Load()
	if err != nil {
		t.Fatalf("empty policy keys must be allowed: %v", err)
	}
	if cfg.PolicyPublicKeysJSON != "" {
		t.Fatalf("PolicyPublicKeysJSON = %q, want empty", cfg.PolicyPublicKeysJSON)
	}
}
