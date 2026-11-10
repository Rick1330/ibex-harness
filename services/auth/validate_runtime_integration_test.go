//go:build integration

package auth_test

import (
	"context"
	"database/sql"
	"errors"
	"net/url"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/infra/migrations/postgres"
	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
	"github.com/google/uuid"
)

const runtimeIntegrationSecret = "runtime-integration-secret"

// TestValidateTokenIntegration_AsRuntime is the guard for the ordering
// invariant in ADR-0098: the validation lookup must work when the service
// connects as ibex_runtime, which cannot read the tokens table directly and
// cannot pin ibex_app while calling the definer. It passes only when
// FindActiveByPrefix reaches ibex_core.auth_find_token_by_prefix.
func TestValidateTokenIntegration_AsRuntime(t *testing.T) {
	dsn, cleanup := testutil.SetupPostgres(t)
	defer cleanup()

	ownerDB := testutil.OpenDB(t, dsn)
	defer func() { _ = ownerDB.Close() }()
	seedRepo := repository.RequireTokensRepository(t, ownerDB, nil)
	orgID := testutil.SeedOrganization(t, ownerDB, "Runtime Org", "runtime-"+uuid.NewString()[:8])

	argon2 := token.TestArgon2Params()
	active := seedRuntimeBearer(t, seedRepo, orgID, runtimeSeed{})
	revoked := seedRuntimeBearer(t, seedRepo, orgID, runtimeSeed{revoked: true})
	expiredAt := time.Now().UTC().Add(-time.Hour)
	expired := seedRuntimeBearer(t, seedRepo, orgID, runtimeSeed{expiresAt: &expiredAt})

	provisionRuntimeLogin(t, dsn)
	runtimeDB := openRuntimeDB(t, dsn)
	defer func() { _ = runtimeDB.Close() }()

	validator := newRuntimeValidator(t, runtimeDB, argon2)

	resp, err := validator.Validate(context.Background(), active)
	if err != nil {
		t.Fatalf("active token as ibex_runtime: %v", err)
	}
	if resp.GetOrgId() != orgID {
		t.Fatalf("org_id = %s, want %s", resp.GetOrgId(), orgID)
	}
	if resp.GetPermissions() != 11 {
		t.Fatalf("permissions = %d, want 11", resp.GetPermissions())
	}

	assertRuntimeUnauthenticated(t, validator, revoked, "revoked")
	assertRuntimeUnauthenticated(t, validator, expired, "expired")
	assertRuntimeUnauthenticated(t, validator, "ibex_pat_"+uuid.NewString()+"_unknown", "unknown prefix")
}

// provisionRuntimeLogin gives the capability logins a SCRAM verifier and clears
// their connection limit. The secrets are test-only and pairwise distinct from
// the owner credential in the test DSN.
func provisionRuntimeLogin(t *testing.T, dsn string) {
	t.Helper()
	t.Setenv("IBEX_RUNTIME_DB_PASSWORD", runtimeIntegrationSecret)
	t.Setenv("IBEX_WORKER_DB_PASSWORD", runtimeIntegrationSecret+"-worker")
	t.Setenv("IBEX_BOOTSTRAP_DB_PASSWORD", runtimeIntegrationSecret+"-bootstrap")
	if err := postgres.Provision(dsn); err != nil {
		t.Fatalf("Provision capability logins: %v", err)
	}
}

// openRuntimeDB connects with the ibex_runtime credential.
func openRuntimeDB(t *testing.T, dsn string) *sql.DB {
	t.Helper()
	parsed, err := url.Parse(dsn)
	if err != nil {
		t.Fatalf("parse test DSN: %v", err)
	}
	parsed.User = url.UserPassword("ibex_runtime", runtimeIntegrationSecret)
	db, err := sql.Open("postgres", parsed.String())
	if err != nil {
		t.Fatalf("open runtime pool: %v", err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := db.PingContext(ctx); err != nil {
		t.Fatalf("connect as ibex_runtime: %v", err)
	}
	return db
}

func newRuntimeValidator(t *testing.T, db *sql.DB, argon2 token.Argon2Params) *token.Validator {
	t.Helper()
	repo := repository.RequireTokensRepository(t, db, nil)
	lookup, err := token.NewRepoLookup(repo)
	if err != nil {
		t.Fatalf("NewRepoLookup: %v", err)
	}
	validator, err := token.NewValidator(lookup, argon2)
	if err != nil {
		t.Fatalf("NewValidator: %v", err)
	}
	return validator
}

// runtimeSeed is the token state a runtime-validation case needs.
type runtimeSeed struct {
	revoked   bool
	expiresAt *time.Time
}

func seedRuntimeBearer(t *testing.T, repo *repository.TokensRepository, orgID string, seed runtimeSeed) string {
	t.Helper()
	tokenID := uuid.New()
	bearer := "ibex_pat_" + tokenID.String() + "_runtimesecret"
	hash, err := token.HashForTest(bearer, token.TestArgon2Params())
	if err != nil {
		t.Fatalf("hash bearer: %v", err)
	}
	if _, err := repo.InsertTestToken(context.Background(), repository.TestTokenParams{
		OrgID: orgID, Prefix: "ibex_pat_" + tokenID.String(), Hash: hash, Name: "runtime",
		Permissions: 11, Revoked: seed.revoked, ExpiresAt: seed.expiresAt,
	}); err != nil {
		t.Fatalf("insert token: %v", err)
	}
	return bearer
}

func assertRuntimeUnauthenticated(t *testing.T, validator *token.Validator, bearer, label string) {
	t.Helper()
	_, err := validator.Validate(context.Background(), bearer)
	if !errors.Is(err, token.ErrUnauthenticated) {
		t.Fatalf("%s token: err = %v, want ErrUnauthenticated", label, err)
	}
}
