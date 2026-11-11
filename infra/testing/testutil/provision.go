//go:build integration

package testutil

import (
	"testing"

	"github.com/Rick1330/ibex-harness/infra/testing/pgprovision"
	"github.com/Rick1330/ibex-harness/infra/testing/testcreds"
)

// Capability-login secrets for tests that provision the runtime, worker,
// bootstrap and auth logins. Roles and their passwords are cluster-global, so
// every integration package that provisions must use the same values: two
// packages provisioning the same role with different secrets invalidate each
// other's connection, and `go test ./...` runs package binaries in parallel. The
// values live in testcreds because this package imports the migration package
// and the migration tests are inside it; re-exporting keeps the existing call
// sites reading from one source of truth.
const (
	RuntimeLoginTestPassword   = testcreds.RuntimeLoginTestPassword
	WorkerLoginTestPassword    = testcreds.WorkerLoginTestPassword
	BootstrapLoginTestPassword = testcreds.BootstrapLoginTestPassword
	AuthLoginTestPassword      = testcreds.AuthLoginTestPassword
)

// SetProvisionEnv exports the capability-login secrets Provision reads.
func SetProvisionEnv(t *testing.T) {
	t.Helper()
	testcreds.SetProvisionEnv(t)
}

// ProvisionCapabilityLogins delegates to the proto-free leaf package so callers
// that cannot import this package can still provision the logins.
func ProvisionCapabilityLogins(t *testing.T, dsn string) {
	t.Helper()
	pgprovision.CapabilityLogins(t, dsn)
}
