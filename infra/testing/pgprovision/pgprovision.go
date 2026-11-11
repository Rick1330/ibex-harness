//go:build integration

// Package pgprovision provisions the capability logins for integration tests.
//
// It exists as a leaf so a package can provision without importing
// infra/testing/testutil, whose grpc_seed.go needs generated protobuf. It
// imports the migration package (which is proto-free) directly; the advisory
// lock keeps package binaries that share one cluster from racing each other.
package pgprovision

import (
	"context"
	"database/sql"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/infra/migrations/postgres"
	"github.com/Rick1330/ibex-harness/infra/testing/testcreds"
)

const (
	// provisionLockKey serialises capability provisioning across package
	// binaries. It is 0x69626578, "ibex" in ASCII.
	provisionLockKey int64 = 0x69626578
	// provisionLockTimeout bounds the wait for that lock, so a stuck holder
	// fails the test instead of hanging it.
	provisionLockTimeout = 60 * time.Second
)

// CapabilityLogins gives the capability logins a SCRAM verifier and clears
// their connection limit. Provision alters cluster-global role rows, so the
// call is serialised across package binaries: two packages entering it at once
// make one of them fail with "tuple concurrently updated" (SQLSTATE XX000).
func CapabilityLogins(t *testing.T, dsn string) {
	t.Helper()
	testcreds.SetProvisionEnv(t)
	release := lockProvisioning(t, dsn)
	defer release()
	if err := postgres.Provision(dsn); err != nil {
		t.Fatalf("Provision capability logins: %v", err)
	}
}

// lockProvisioning blocks until this process holds the provisioning lock and
// returns its release. The lock is session-scoped on a dedicated connection, so
// it is independent of Provision's own transaction and cannot be released by
// it.
func lockProvisioning(t *testing.T, dsn string) func() {
	t.Helper()
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		t.Fatalf("open provisioning-lock pool: %v", err)
	}
	conn, err := db.Conn(context.Background())
	if err != nil {
		_ = db.Close()
		t.Fatalf("open provisioning-lock connection: %v", err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), provisionLockTimeout)
	defer cancel()
	// nosemgrep: go_sql_rule-concat-sqli -- constant advisory-lock statement; the key is a bound parameter.
	if _, err := conn.ExecContext(ctx, `SELECT pg_advisory_lock($1)`, provisionLockKey); err != nil {
		_ = conn.Close()
		_ = db.Close()
		t.Fatalf("wait for provisioning lock: %v", err)
	}
	return func() {
		// nosemgrep: go_sql_rule-concat-sqli -- constant advisory-unlock statement; the key is a bound parameter.
		_, _ = conn.ExecContext(context.Background(), `SELECT pg_advisory_unlock($1)`, provisionLockKey)
		_ = conn.Close()
		_ = db.Close()
	}
}
