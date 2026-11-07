package config

import "testing"

// ambientProxyEnvVars are variables a developer shell or CI job may export that
// would otherwise leak into a case that does not set them. Clearing them keeps
// the "unset" cases honest: without this, an ambient
// IBEX_CONTEXT_GRPC_SERVICE_TOKEN makes TestLoad/context_disabled_needs_no_service_token
// fail and TestLoad/context_enabled_without_service_token pass for the wrong
// reason.
var ambientProxyEnvVars = []string{
	"IBEX_CONTEXT_GRPC_SERVICE_TOKEN",
	"IBEX_CONTEXT_COLOCATED",
	"IBEX_AUTH_GRPC_CA_FILE",
}

// withProxyEnv applies the case environment after clearing ambient variables.
// t.Setenv restores every value on cleanup and forbids t.Parallel, so callers
// must stay sequential (TestLoad is).
func withProxyEnv(t *testing.T, env map[string]string) {
	t.Helper()
	for _, key := range ambientProxyEnvVars {
		t.Setenv(key, "")
	}
	for k, v := range env {
		t.Setenv(k, v)
	}
}
