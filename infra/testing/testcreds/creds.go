//go:build integration

// Package testcreds holds the capability-login credentials that every
// integration package which provisions the cluster-global roles must share.
//
// It deliberately imports nothing from this repository. The Postgres helper
// package testutil imports the migration package, and the migration tests live
// inside that package, so credentials funnelled through testutil would form an
// import cycle (postgres [test] -> testutil -> postgres) that Go rejects. A leaf
// package gives both sides one source of truth without one.
package testcreds

import "testing"

// Capability-login secrets for tests that provision the runtime, worker,
// bootstrap and auth logins. Roles and their passwords are cluster-global, so
// every integration package that provisions must use the same values: two
// packages provisioning the same role with different secrets invalidate each
// other's connection, and `go test ./...` runs package binaries in parallel.
// Provision rejects a secret that is blank, non-ASCII, contains a space, equals
// the owner credential, or repeats another capability secret, so the four
// values below are pairwise distinct and differ from the DSN credential.
const (
	RuntimeLoginTestPassword   = "capability-test-only-runtime"
	WorkerLoginTestPassword    = "capability-test-only-worker"
	BootstrapLoginTestPassword = "capability-test-only-bootstrap"
	AuthLoginTestPassword      = "capability-test-only-auth"
)

// SetProvisionEnv exports the capability-login secrets Provision reads.
func SetProvisionEnv(t *testing.T) {
	t.Helper()
	t.Setenv("IBEX_RUNTIME_DB_PASSWORD", RuntimeLoginTestPassword)
	t.Setenv("IBEX_WORKER_DB_PASSWORD", WorkerLoginTestPassword)
	t.Setenv("IBEX_BOOTSTRAP_DB_PASSWORD", BootstrapLoginTestPassword)
	t.Setenv("IBEX_AUTH_DB_PASSWORD", AuthLoginTestPassword)
}
