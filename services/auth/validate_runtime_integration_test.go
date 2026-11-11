//go:build integration

package auth_test

import (
	"context"
	"database/sql"
	"errors"
	"net/url"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
	"github.com/google/uuid"
	"github.com/lib/pq"
)

// TestValidateTokenIntegration_AsAuth is the guard for the ordering invariant
// in ADR-0098 and for migration 000068: the validation lookup must work when
// the service connects as ibex_auth, which cannot read the tokens table
// directly and cannot pin ibex_app while calling the definer. It passes only
// when FindActiveByPrefix reaches ibex_core.auth_find_token_by_prefix.
func TestValidateTokenIntegration_AsAuth(t *testing.T) {
	dsn, cleanup := testutil.SetupPostgres(t)
	defer cleanup()

	ownerDB := testutil.OpenDB(t, dsn)
	defer func() { _ = ownerDB.Close() }()
	seedRepo := repository.RequireTokensRepository(t, ownerDB, nil)
	orgID := testutil.SeedOrganization(t, ownerDB, "Auth Org", "auth-"+uuid.NewString()[:8])

	argon2 := token.TestArgon2Params()
	active := seedRuntimeBearer(t, seedRepo, orgID, runtimeSeed{})
	revoked := seedRuntimeBearer(t, seedRepo, orgID, runtimeSeed{revoked: true})
	expiredAt := time.Now().UTC().Add(-time.Hour)
	expired := seedRuntimeBearer(t, seedRepo, orgID, runtimeSeed{expiresAt: &expiredAt})

	testutil.ProvisionCapabilityLogins(t, dsn)
	authDB := openCapabilityDB(t, dsn, "ibex_auth", testutil.AuthLoginTestPassword)
	defer func() { _ = authDB.Close() }()

	validator := newCapabilityValidator(t, authDB, argon2)

	resp, err := validator.Validate(context.Background(), active)
	if err != nil {
		t.Fatalf("active token as ibex_auth: %v", err)
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

	// The split exists for this: ibex_runtime keeps full tenant access but must
	// no longer be able to resolve a bearer, because 000068 moved EXECUTE on the
	// reader to ibex_auth and revoked it from ibex_runtime in the same
	// transaction.
	assertRuntimeCannotResolve(t, dsn, active)
}

// openCapabilityDB connects with one provisioned capability login.
func openCapabilityDB(t *testing.T, dsn, login, password string) *sql.DB {
	t.Helper()
	parsed, err := url.Parse(dsn)
	if err != nil {
		t.Fatalf("parse test DSN: %v", err)
	}
	parsed.User = url.UserPassword(login, password)
	db, err := sql.Open("postgres", parsed.String())
	if err != nil {
		t.Fatalf("open %s pool: %v", login, err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := db.PingContext(ctx); err != nil {
		t.Fatalf("connect as %s: %v", login, err)
	}
	return db
}

// assertRuntimeCannotResolve requires the deployed grant split: ibex_runtime
// is refused the token reader with SQLSTATE 42501, not with a miss. A miss
// would mean the definer ran for a login that should not reach it.
func assertRuntimeCannotResolve(t *testing.T, dsn, bearer string) {
	t.Helper()
	runtimeDB := openCapabilityDB(t, dsn, "ibex_runtime", testutil.RuntimeLoginTestPassword)
	defer func() { _ = runtimeDB.Close() }()

	parsed, err := token.ParsePAT(bearer)
	if err != nil {
		t.Fatalf("parse bearer: %v", err)
	}
	repo := repository.RequireTokensRepository(t, runtimeDB, nil)
	row, err := repo.FindActiveByPrefix(context.Background(), parsed.Prefix)
	if err == nil {
		t.Fatalf(
			"ibex_runtime resolved token %s; 000068 must revoke EXECUTE on the reader from it",
			row.ID,
		)
	}
	var pqErr *pq.Error
	if !errors.As(err, &pqErr) || pqErr.Code != "42501" {
		t.Fatalf("ibex_runtime lookup error = %v, want SQLSTATE 42501", err)
	}
}

// newCapabilityValidator builds a validator over a pool opened as a capability
// login, so the definer call and the role grant are exercised, not just the Go
// SQL.
func newCapabilityValidator(t *testing.T, db *sql.DB, argon2 token.Argon2Params) *token.Validator {
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

// seedRuntimeBearer inserts the token described by seed for orgID and returns
// the bearer the validator is called with.
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

// assertRuntimeUnauthenticated requires a rejected bearer to fail as
// unauthenticated, which is the same answer a wrong token gets under the owner
// login; the definer must not turn a miss into a different error.
func assertRuntimeUnauthenticated(t *testing.T, validator *token.Validator, bearer, label string) {
	t.Helper()
	_, err := validator.Validate(context.Background(), bearer)
	if !errors.Is(err, token.ErrUnauthenticated) {
		t.Fatalf("%s token: err = %v, want ErrUnauthenticated", label, err)
	}
}
