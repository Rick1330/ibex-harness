//go:build integration

package testutil

import (
	"context"
	"database/sql"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/infra/migrations/postgres"
)

// Capability-login secrets for tests that provision the runtime, worker and
// bootstrap logins. Roles and their passwords are cluster-global, so every
// integration package that provisions must use the same values: two packages
// provisioning the same role with different secrets invalidate each other's
// connection, and `go test ./...` runs package binaries in parallel. Provision
// rejects a secret that is blank, non-ASCII, contains a space, equals the owner
// credential, or repeats another capability secret, so the three values below
// are pairwise distinct and differ from the DSN credential.
const (
	RuntimeLoginTestPassword   = "capability-test-only-runtime"
	WorkerLoginTestPassword    = "capability-test-only-worker"
	BootstrapLoginTestPassword = "capability-test-only-bootstrap"
)

const (
	// provisionLockKey serialises capability provisioning across package
	// binaries. It is 0x69626578, "ibex" in ASCII.
	provisionLockKey int64 = 0x69626578
	// provisionLockTimeout bounds the wait for that lock, so a stuck holder
	// fails the test instead of hanging it.
	provisionLockTimeout = 60 * time.Second
)

// SetProvisionEnv exports the capability-login secrets Provision reads.
func SetProvisionEnv(t *testing.T) {
	t.Helper()
	t.Setenv("IBEX_RUNTIME_DB_PASSWORD", RuntimeLoginTestPassword)
	t.Setenv("IBEX_WORKER_DB_PASSWORD", WorkerLoginTestPassword)
	t.Setenv("IBEX_BOOTSTRAP_DB_PASSWORD", BootstrapLoginTestPassword)
}

// ProvisionCapabilityLogins gives the capability logins a SCRAM verifier and
// clears their connection limit, using the shared credentials above. Provision
// alters cluster-global role rows, so the call is serialised across package
// binaries: two packages entering it at once make one of them fail with
// "tuple concurrently updated" (SQLSTATE XX000), which looks like a real
// regression in whatever suite lost the race.
func ProvisionCapabilityLogins(t *testing.T, dsn string) {
	t.Helper()
	SetProvisionEnv(t)
	release := lockCapabilityProvisioning(t, dsn)
	defer release()
	if err := postgres.Provision(dsn); err != nil {
		t.Fatalf("Provision capability logins: %v", err)
	}
}

// lockCapabilityProvisioning blocks until this process holds the provisioning
// lock and returns its release. The lock is session-scoped on a dedicated
// connection, so it is independent of Provision's own transaction and cannot be
// released by it. Advisory locks are scoped to a database, which is the same
// database every integration package resolves from POSTGRES_TEST_DSN.
func lockCapabilityProvisioning(t *testing.T, dsn string) func() {
	t.Helper()
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		t.Fatalf("open provisioning-lock pool: %v", err)
	}
	// The connection outlives the acquisition deadline: release closes it, not
	// context cancellation.
	conn, err := db.Conn(context.Background())
	if err != nil {
		_ = db.Close()
		t.Fatalf("open provisioning-lock connection: %v", err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), provisionLockTimeout)
	defer cancel()
	if _, err := conn.ExecContext(ctx, `SELECT pg_advisory_lock($1)`, provisionLockKey); err != nil {
		_ = conn.Close()
		_ = db.Close()
		t.Fatalf("wait for provisioning lock: %v", err)
	}
	return func() {
		// Closing the session releases the advisory lock; unlocking first keeps
		// the release explicit rather than relying on pool behaviour.
		_, _ = conn.ExecContext(context.Background(), `SELECT pg_advisory_unlock($1)`, provisionLockKey)
		_ = conn.Close()
		_ = db.Close()
	}
}
