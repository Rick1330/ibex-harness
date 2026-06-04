//go:build integration

package testutil

import (
	"os"
	"testing"

	"github.com/Rick1330/ibex-harness/infra/migrations/postgres"
)

const defaultComposeTestDSN = "postgres://ibex:ibex@localhost:5433/ibex_test?sslmode=disable"

// SetupPostgres returns a migrated Postgres DSN and a cleanup function.
// Uses compose test stack (POSTGRES_TEST_DSN or port 5433). Set IBEX_USE_TESTCONTAINERS=1 only
// after optional testcontainers module is wired (see docs/DEPENDENCIES.md §8.2.1); until then it skips.
func SetupPostgres(t testing.TB) (dsn string, cleanup func()) {
	t.Helper()
	if os.Getenv("IBEX_USE_TESTCONTAINERS") == "1" {
		t.Skip("testcontainers mode not linked in root go.mod yet; use make compose-test-up")
	}
	dsn = resolveComposeDSN()
	if err := postgres.Up(dsn); err != nil {
		t.Fatalf("migrate up: %v", err)
	}
	return dsn, func() {}
}

func resolveComposeDSN() string {
	if dsn := os.Getenv("POSTGRES_TEST_DSN"); dsn != "" {
		return dsn
	}
	return defaultComposeTestDSN
}
