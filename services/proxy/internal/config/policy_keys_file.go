package config

import (
	"fmt"
	"os"
	"strings"
)

// applyPolicyPublicKeysFile fills the optional policy public key set from a
// file when IBEX_PROXY_POLICY_PUBLIC_KEYS is empty. Compose cannot carry a
// multi-line PEM JSON object in a .env file, which is why the file form exists.
// The inline value wins, and an unset pair still disables the policy stage.
func applyPolicyPublicKeysFile(envCfg *envConfig) error {
	if strings.TrimSpace(envCfg.PolicyPublicKeysJSON) != "" {
		return nil
	}
	path := strings.TrimSpace(envCfg.PolicyPublicKeysFile)
	if path == "" {
		return nil
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return fmt.Errorf("IBEX_PROXY_POLICY_PUBLIC_KEYS_FILE: cannot read file %q: %w", path, err)
	}
	raw := strings.TrimSpace(string(data))
	if raw == "" {
		return fmt.Errorf("IBEX_PROXY_POLICY_PUBLIC_KEYS_FILE: file %q is empty", path)
	}
	envCfg.PolicyPublicKeysJSON = raw
	return nil
}
