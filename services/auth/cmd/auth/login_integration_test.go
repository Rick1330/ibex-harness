//go:build integration

package main

import (
	"net/url"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	"github.com/Rick1330/ibex-harness/services/auth/internal/config"
)

// TestIntegration_AuthStartupRejectsWrongLogin proves the startup check against
// a real server: the owner DSN the harness provides must fail startup, and the
// provisioned ibex_auth capability login must pass it. Every rejection names the
// expected login, so a harness DSN that is neither owner nor superuser still
// fails the first half for the right reason.
func TestIntegration_AuthStartupRejectsWrongLogin(t *testing.T) {
	dsn, cleanup := testutil.SetupPostgres(t)
	defer cleanup()

	ownerDB, err := openVerifiedAuthPostgres(config.Config{PostgresDSN: dsn})
	if err == nil {
		_ = ownerDB.Close()
		t.Fatal("auth startup must reject a DSN that is not the ibex_auth capability login")
	}
	if !strings.Contains(err.Error(), authCapabilityLogin) {
		t.Fatalf("startup error must name the expected login, got %v", err)
	}
	t.Logf("auth startup rejected the owner DSN: %v", err)

	testutil.ProvisionCapabilityLogins(t, dsn)
	authDSN := capabilityDSN(t, dsn, authCapabilityLogin, testutil.AuthLoginTestPassword)
	authDB, err := openVerifiedAuthPostgres(config.Config{PostgresDSN: authDSN})
	if err != nil {
		t.Fatalf("auth startup must accept the ibex_auth capability login: %v", err)
	}
	t.Cleanup(func() { _ = authDB.Close() })
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
