//go:build integration

package bootstrap

import (
	"net/url"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
)

// TestIntegration_OpenProxyPostgres_RejectsWrongLogin proves the startup check
// against a real server: the owner DSN the harness provides must fail pool
// startup, and the provisioned ibex_runtime capability login must pass it.
func TestIntegration_OpenProxyPostgres_RejectsWrongLogin(t *testing.T) {
	dsn, cleanup := testutil.SetupPostgres(t)
	defer cleanup()

	ownerDB, err := openProxyPostgres(dsn)
	if err == nil {
		_ = ownerDB.Close()
		t.Fatal("proxy startup must reject a DSN that is not the ibex_runtime capability login")
	}
	if !strings.Contains(err.Error(), runtimeCapabilityLogin) {
		t.Fatalf("startup error must name the expected login, got %v", err)
	}
	t.Logf("proxy startup rejected the owner DSN: %v", err)

	testutil.ProvisionCapabilityLogins(t, dsn)
	runtimeDSN := capabilityDSN(t, dsn, runtimeCapabilityLogin, testutil.RuntimeLoginTestPassword)
	runtimeDB, err := openProxyPostgres(runtimeDSN)
	if err != nil {
		t.Fatalf("proxy startup must accept the ibex_runtime capability login: %v", err)
	}
	t.Cleanup(func() { _ = runtimeDB.Close() })
}

// capabilityDSN re-points the harness DSN at one provisioned capability login.
func capabilityDSN(t *testing.T, dsn, login, password string) string {
	t.Helper()
	parsed, err := url.Parse(dsn)
	if err != nil {
		t.Fatalf("parse test DSN: %v", err)
	}
	parsed.User = url.UserPassword(login, password)
	return parsed.String()
}
