//go:build integration

package bootstrap

import (
	"database/sql"
	"path/filepath"
	"testing"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
)

// This file is the harness the bootstrap integration tests share: the migrated
// compose database the fixtures write through, and the configuration one
// fixture starts from. The tests themselves live in the sibling files, grouped
// by the concern each one proves, so a failure names what it covers. The fault
// tests have their own harness in bootstrap_fault_harness_test.go, because they
// never reach a database.

// openIntegrationDB returns a pool against the migrated compose test database,
// with the DSN for the tests that also open a second, differently-privileged
// pool. Both cleanups are registered here so the pool outlives the rows a
// caller removes in its own cleanup: cleanups run last-registered-first, so the
// caller's row cleanup runs before this file's close, and the setup cleanup
// runs last of all.
func openIntegrationDB(t *testing.T) (*sql.DB, string) {
	t.Helper()
	dsn, cleanup := testutil.SetupPostgres(t)
	t.Cleanup(cleanup)

	db, err := sql.Open("postgres", dsn)
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	t.Cleanup(func() { _ = db.Close() })
	return db, dsn
}

// newBootstrapConfig is a valid first-run configuration for one organization:
// the owner identity, their default agent, and the file the bootstrap PAT is
// written to. The caller sets the fields its scenario varies on the returned
// value: OrgName names the scenario, AllowSecondOrg states that a second tenant
// is intended, and MemoryToken adds a memory-service bearer. MemoryToken is
// left empty because supplying one switches createIdentity to writing a
// service_token row, so it is a scenario choice rather than a fixture default.
//
// The identity values are stated here rather than read from the package
// defaults, so a change to a default cannot silently satisfy a test that meant
// to pin the value it asserts.
func newBootstrapConfig(t *testing.T, dsn, slug, email string) bootstrapConfig {
	t.Helper()
	return bootstrapConfig{
		PostgresDSN: dsn,
		OrgName:     "Bootstrap Test",
		OrgSlug:     slug,
		UserEmail:   email,
		UserName:    "Owner",
		AgentName:   "Default Agent",
		AgentSlug:   "default",
		PATName:     "Bootstrap PAT",
		PATFile:     filepath.Join(t.TempDir(), "bootstrap.pat"),
	}
}
