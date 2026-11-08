package config

import (
	"fmt"
	"os"
	"strings"

	ibexconfig "github.com/Rick1330/ibex-harness/packages/config"
)

// applyPEMFileEnv fills PEM fields from file-backed env vars when the inline
// value is empty. Inline PEM always wins, so the existing environment contract
// is unchanged. Compose cannot carry a multi-line PEM in a .env file, which is
// why the file form exists.
func applyPEMFileEnv(envCfg *envConfig) error {
	jwt, err := resolvePEM(envCfg.JWTPrivateKeyPEM.String(), envCfg.JWTPrivateKeyFile, "JWT_PRIVATE_KEY_FILE")
	if err != nil {
		return err
	}
	if jwt != "" {
		envCfg.JWTPrivateKeyPEM = ibexconfig.Secret(jwt)
	}

	policy, err := resolvePEM(
		envCfg.PolicySigningKeyPEM.String(),
		envCfg.PolicySigningKeyFile,
		"IBEX_AUTH_POLICY_SIGNING_KEY_FILE",
	)
	if err != nil {
		return err
	}
	if policy != "" {
		envCfg.PolicySigningKeyPEM = ibexconfig.Secret(policy)
	}
	return nil
}

// resolvePEM returns the inline value when present, otherwise the file value.
func resolvePEM(inline, filePath, envVar string) (string, error) {
	if strings.TrimSpace(inline) != "" {
		return inline, nil
	}
	return readPEMFileEnv(envVar, filePath)
}

// readPEMFileEnv reads and trims a PEM file. An empty path means "not
// configured" and returns an empty string. A configured but unreadable or
// empty file is a startup error and names the environment variable, never the
// file contents.
func readPEMFileEnv(envVar, path string) (string, error) {
	path = strings.TrimSpace(path)
	if path == "" {
		return "", nil
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return "", fmt.Errorf("%s: cannot read PEM file %q: %w", envVar, path, err)
	}
	pem := strings.TrimSpace(string(data))
	if pem == "" {
		return "", fmt.Errorf("%s: PEM file %q is empty", envVar, path)
	}
	return pem, nil
}
