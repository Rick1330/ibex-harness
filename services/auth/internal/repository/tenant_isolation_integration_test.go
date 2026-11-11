//go:build integration

package repository_test

import (
	"context"
	"database/sql"
	"errors"
	"net/url"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/google/uuid"
	"github.com/lib/pq"
)

// isolationFixture holds two tenants and one row each for the repositories
// under test. The repositories run on the ibex_auth pool; the rows were seeded
// through the owner pool.
type isolationFixture struct {
	repo   *repository.TokensRepository
	users  *repository.UsersRepository
	agents *repository.AgentsRepository
	totp   *repository.TotpSecretRepo
	creds  *repository.ProviderCredentialsRepository

	// authDB is the pool the repositories above were built on. The
	// RLS-versus-WHERE case needs to open its own transaction on it.
	authDB *sql.DB
	// dsn is the owner DSN the fixture was built from, so a test can reopen the
	// same database as another capability login.
	dsn string

	orgA, orgB     string
	userA, userB   string
	agentB         string
	tokenA         string
	tokenAPrefix   string
	tokenBPrefix   string
	totpBCipher    []byte
	credName       string
	credCiphertext []byte
}

// isolationSeedRepos are the repositories used to create the fixture rows.
// They are bound to the owner pool because seeding needs privileges the
// runtime login deliberately does not have.
type isolationSeedRepos struct {
	tokens *repository.TokensRepository
	totp   *repository.TotpSecretRepo
	creds  *repository.ProviderCredentialsRepository
}

// newIsolationFixture seeds two organisations and their rows through the owner
// pool, provisions the capability logins, and binds every repository under test
// to a second pool opened as ibex_auth.
func newIsolationFixture(t *testing.T) *isolationFixture {
	t.Helper()
	dsn, cleanup := testutil.SetupPostgres(t)
	t.Cleanup(cleanup)
	ownerDB := testutil.OpenDB(t, dsn)
	t.Cleanup(func() { _ = ownerDB.Close() })

	label := uuid.NewString()[:8]
	orgA := testutil.SeedOrganization(t, ownerDB, "Isolation A "+label, "iso-a-"+label)
	orgB := testutil.SeedOrganization(t, ownerDB, "Isolation B "+label, "iso-b-"+label)
	userA := testutil.SeedUser(t, ownerDB, orgA, "iso-a-"+label+"@test.local", "User A")
	userB := testutil.SeedUser(t, ownerDB, orgB, "iso-b-"+label+"@test.local", "User B")
	agentB := testutil.SeedAgent(t, ownerDB, orgB, userB, "Agent B", "agent-b-"+label)

	seedCreds, err := repository.NewProviderCredentialsRepository(ownerDB, nil)
	if err != nil {
		t.Fatalf("NewProviderCredentialsRepository (seed): %v", err)
	}
	f := &isolationFixture{
		orgA: orgA, orgB: orgB, userA: userA, userB: userB, agentB: agentB,
		credName: "openai", credCiphertext: []byte("org-b-secret"), dsn: dsn,
	}
	f.seedRows(t, &isolationSeedRepos{
		tokens: repository.RequireTokensRepository(t, ownerDB, nil),
		totp:   repository.NewTotpSecretRepo(ownerDB),
		creds:  seedCreds,
	})

	testutil.ProvisionCapabilityLogins(t, dsn)
	authDB := openIsolationAuthDB(t, dsn)
	t.Cleanup(func() { _ = authDB.Close() })
	f.bindCapabilityRepos(t, authDB)
	return f
}

// seedRows creates org B's token, TOTP secret and provider credential, plus a
// token for org A so the listing has something of its own to return.
func (f *isolationFixture) seedRows(t *testing.T, seeds *isolationSeedRepos) {
	t.Helper()
	ctx := context.Background()
	prefixA := "ibex_pat_" + uuid.NewString()
	idA, err := seeds.tokens.InsertTestToken(ctx, repository.TestTokenParams{
		OrgID: f.orgA, Prefix: prefixA, Hash: "hash-a-" + uuid.NewString(), Name: "a", Permissions: 1,
	})
	if err != nil {
		t.Fatalf("seed token A: %v", err)
	}
	f.tokenA = idA
	f.tokenAPrefix = prefixA
	prefixB := "ibex_pat_" + uuid.NewString()
	if _, err := seeds.tokens.InsertTestToken(ctx, repository.TestTokenParams{
		OrgID: f.orgB, Prefix: prefixB, Hash: "hash-b-" + uuid.NewString(), Name: "b", Permissions: 1,
	}); err != nil {
		t.Fatalf("seed token B: %v", err)
	}
	f.tokenBPrefix = prefixB
	f.totpBCipher = []byte("org-b-totp")
	if err := seeds.totp.UpsertPending(ctx, repository.TotpSecretRow{
		OrgID: f.orgB, UserID: f.userB, Ciphertext: f.totpBCipher,
		WrappedDEK: []byte("dek-b"), EncryptionKeyID: "v1",
	}); err != nil {
		t.Fatalf("seed TOTP B: %v", err)
	}
	if _, err := seeds.creds.Upsert(ctx, repository.ProviderCredentialRow{
		OrgID: f.orgB, ProviderName: f.credName, Ciphertext: f.credCiphertext,
		WrappedDEK: []byte("dek-b"), EncryptionKeyID: "v1", KeyHint: "hint", Status: "active",
	}); err != nil {
		t.Fatalf("seed credential B: %v", err)
	}
}

// bindCapabilityRepos moves every repository under test onto the ibex_auth
// pool. The capability login has no table grants of its own, so each operation
// succeeds only when withTenant pins ibex_app.
func (f *isolationFixture) bindCapabilityRepos(t *testing.T, db *sql.DB) {
	t.Helper()
	creds, err := repository.NewProviderCredentialsRepository(db, nil)
	if err != nil {
		t.Fatalf("NewProviderCredentialsRepository (auth): %v", err)
	}
	f.authDB = db
	f.repo = repository.RequireTokensRepository(t, db, nil)
	f.users = repository.NewUsersRepository(db, nil)
	f.agents = repository.NewAgentsRepository(db, nil)
	f.totp = repository.NewTotpSecretRepo(db)
	f.creds = creds
}

// openIsolationAuthDB connects with the ibex_auth credential.
func openIsolationAuthDB(t *testing.T, dsn string) *sql.DB {
	t.Helper()
	parsed, err := url.Parse(dsn)
	if err != nil {
		t.Fatalf("parse test DSN: %v", err)
	}
	parsed.User = url.UserPassword("ibex_auth", testutil.AuthLoginTestPassword)
	db, err := sql.Open("postgres", parsed.String())
	if err != nil {
		t.Fatalf("open auth pool: %v", err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := db.PingContext(ctx); err != nil {
		t.Fatalf("connect as ibex_auth: %v", err)
	}
	return db
}

// TestRepositoryCrossTenantNegatives runs every tenant operation on a pool
// opened as ibex_auth, the login the service uses in production. The auth login
// has no table grants and no EXECUTE on the privileged readers beyond what the
// migrations grant, so each case succeeds only because
// withTenant pins SET LOCAL ROLE ibex_app and app.current_org_id for that
// transaction. The queries are pinned to org A while they name org B's rows, so
// a miss is the expected answer. A SQLSTATE 42501 from any case means the pin
// is broken, not that the tenant is isolated: the operation never reached
// ibex_app, and the "miss" would be an outage disguised as a cross-tenant
// denial.
func TestRepositoryCrossTenantNegatives(t *testing.T) {
	f := newIsolationFixture(t)
	ctx := context.Background()
	for _, tc := range crossTenantCases(ctx, f) {
		t.Run(tc.name, tc.run)
	}
}

// crossTenantCaseTable is one cross-tenant operation per repository.
type crossTenantCaseTable struct {
	name string
	run  func(*testing.T)
}

// crossTenantCases returns one case per tenant operation, each attempting to
// reach org B's row while scoped to org A.
func crossTenantCases(ctx context.Context, f *isolationFixture) []crossTenantCaseTable {
	return []crossTenantCaseTable{
		{"user", func(t *testing.T) {
			assertCrossTenantMiss(t, "user", func() (bool, error) {
				rec, err := f.users.GetByIDAndOrg(ctx, uuid.MustParse(f.userB), uuid.MustParse(f.orgA))
				return rec != nil, err
			})
		}},
		{"agent", func(t *testing.T) {
			assertCrossTenantMiss(t, "agent", func() (bool, error) {
				rec, err := f.agents.GetByIDAndOrg(ctx, uuid.MustParse(f.agentB), uuid.MustParse(f.orgA))
				return rec != nil, err
			})
		}},
		{"rls policy ignores named org", func(t *testing.T) { assertRLSPolicyIgnoresNamedOrg(t, f) }},
		{"token list", func(t *testing.T) { assertCrossTenantTokenList(t, ctx, f) }},
		{"token ids by user", func(t *testing.T) {
			assertCrossTenantMiss(t, "token ids", func() (bool, error) {
				ids, err := f.repo.ListActiveTokenIDsByUser(ctx, repository.OrgUserRef{OrgID: f.orgA, UserID: f.userB})
				return len(ids) != 0, err
			})
		}},
		{"token revoke", func(t *testing.T) {
			assertCrossTenantSentinel(t, "token revoke", repository.ErrNotFound, func() error {
				tokenID := lookupTokenID(t, f, f.tokenBPrefix)
				return f.repo.RevokeToken(ctx, repository.RevokeTokenInput{OrgID: f.orgA, TokenID: tokenID})
			})
		}},
		{"totp secret", func(t *testing.T) {
			assertCrossTenantSentinel(t, "TOTP get", repository.ErrTotpSecretNotFound, func() error {
				_, err := f.totp.Get(ctx, f.orgA, f.userB)
				return err
			})
		}},
		{"provider credential find", func(t *testing.T) {
			assertCrossTenantSentinel(t, "provider credential find", repository.ErrProviderCredentialNotFound, func() error {
				_, err := f.creds.FindByOrgProvider(ctx, f.orgA, f.credName)
				return err
			})
		}},
		{"provider credential list", func(t *testing.T) {
			assertCrossTenantMiss(t, "provider credentials", func() (bool, error) {
				rows, err := f.creds.ListByOrg(ctx, f.orgA)
				return len(rows) != 0, err
			})
		}},
		{"provider credential delete", func(t *testing.T) {
			assertCrossTenantSentinel(t, "provider credential delete", repository.ErrProviderCredentialNotFound, func() error {
				return f.creds.Delete(ctx, f.orgA, f.credName)
			})
			if _, err := f.creds.FindByOrgProvider(ctx, f.orgB, f.credName); err != nil {
				t.Fatalf("org B credential was affected: %v", err)
			}
		}},
	}
}

// assertRLSPolicyIgnoresNamedOrg is the only shape that separates the row-level
// policy from the WHERE clause: the transaction is pinned to org B while the
// statement names org A's user and carries no org predicate, so zero rows can
// come only from the policy. No repository method separates the pinned org from
// the org named in the statement, so the query runs in a withTenant-equivalent
// transaction built here: SET LOCAL ROLE ibex_app plus the org B GUC. The
// positive control reads org B's own row in the same transaction, which proves
// the zero for org A is the policy and not a blanket miss from a dead
// connection or a missing grant.
func assertRLSPolicyIgnoresNamedOrg(t *testing.T, f *isolationFixture) {
	t.Helper()
	ctx := context.Background()
	tx, err := f.authDB.BeginTx(ctx, nil)
	if err != nil {
		t.Fatalf("begin RLS probe: %v", err)
	}
	defer func() { _ = tx.Rollback() }()
	// nosemgrep: go_sql_rule-concat-sqli -- the statement is a compile-time constant and every value is a bound parameter.
	if _, err := tx.ExecContext(ctx, `SET LOCAL ROLE ibex_app`); err != nil {
		t.Fatalf("pin ibex_app for RLS probe: %v", err)
	}
	// nosemgrep: go_sql_rule-concat-sqli -- the statement is a compile-time constant and every value is a bound parameter.
	if _, err := tx.ExecContext(ctx, `SELECT set_config('app.current_org_id', $1, true)`, f.orgB); err != nil {
		t.Fatalf("pin org B for RLS probe: %v", err)
	}
	if n := countUserRows(t, ctx, tx, f.userA); n != 0 {
		t.Fatalf("org A user visible while pinned to org B: %d rows", n)
	}
	if n := countUserRows(t, ctx, tx, f.userB); n != 1 {
		t.Fatalf("org B user not visible while pinned to org B: %d rows", n)
	}
}

// countUserRows counts the rows with the given user id in the caller's
// transaction. It names no org, so only the policy can hide a foreign row.
func countUserRows(t *testing.T, ctx context.Context, tx *sql.Tx, userID string) int {
	t.Helper()
	var n int
	// nosemgrep: go_sql_rule-concat-sqli -- the statement is a compile-time constant and every value is a bound parameter.
	err := tx.QueryRowContext(ctx, `SELECT count(*) FROM ibex_core.users WHERE id = $1::uuid`, userID).Scan(&n)
	assertNoPermissionError(t, err)
	if err != nil {
		t.Fatalf("count user rows %s: %v", userID, err)
	}
	return n
}

// assertCrossTenantSentinel requires the operation to fail with want and never
// with a permission error, so an outage cannot pass as a tenant denial.
func assertCrossTenantSentinel(t *testing.T, label string, want error, call func() error) {
	t.Helper()
	err := call()
	assertNoPermissionError(t, err)
	if !errors.Is(err, want) {
		t.Fatalf("cross-tenant %s = %v, want %v", label, err, want)
	}
}

// assertCrossTenantMiss requires the operation to succeed with no row visible
// to the pinned organisation.
func assertCrossTenantMiss(t *testing.T, label string, found func() (bool, error)) {
	t.Helper()
	hit, err := found()
	assertNoPermissionError(t, err)
	if err != nil {
		t.Fatalf("cross-tenant %s: %v", label, err)
	}
	if hit {
		t.Fatalf("org A saw org B %s", label)
	}
}

// assertCrossTenantTokenList requires org A's listing to include its own token
// and none of org B's. The positive half matters: an empty listing caused by a
// broken pin would otherwise look like a clean cross-tenant miss.
func assertCrossTenantTokenList(t *testing.T, ctx context.Context, f *isolationFixture) {
	t.Helper()
	rows, _, err := f.repo.ListTokens(ctx, f.orgA, "", 100)
	assertNoPermissionError(t, err)
	if err != nil {
		t.Fatalf("list tokens: %v", err)
	}
	sawOwn := false
	for _, row := range rows {
		if row.Prefix == f.tokenBPrefix {
			t.Fatalf("org A listed org B token %s", row.Prefix)
		}
		if row.ID == f.tokenA {
			sawOwn = true
		}
	}
	if !sawOwn {
		t.Fatalf("org A listing did not include its own token %s (prefix %s)", f.tokenA, f.tokenAPrefix)
	}
}

// lookupTokenID resolves org B's token id through the cross-tenant definer, so
// the revoke case can name a row org A must not reach.
func lookupTokenID(t *testing.T, f *isolationFixture, prefix string) string {
	t.Helper()
	row, err := f.repo.FindActiveByPrefix(context.Background(), prefix)
	if err != nil {
		t.Fatalf("lookup token %s: %v", prefix, err)
	}
	return row.ID
}

// assertNoPermissionError fails when err is SQLSTATE 42501: a wrong pin must
// surface as a tenant miss, never as a privilege error.
func assertNoPermissionError(t *testing.T, err error) {
	t.Helper()
	var pqErr *pq.Error
	if errors.As(err, &pqErr) && string(pqErr.Code) == "42501" {
		t.Fatalf("operation failed with a permission error, not a tenant miss: %v", err)
	}
}

// TestRepositoryTokenReaderRefusesRuntime is the negative half of migration
// 000068. Every capability login here is a full tenant role through ibex_app,
// so the split is only real if the token reader itself is refused to
// ibex_runtime. The assertion names SQLSTATE 42501 on purpose: a miss or a
// no-rows result would not prove the grant moved.
func TestRepositoryTokenReaderRefusesRuntime(t *testing.T) {
	f := newIsolationFixture(t)
	runtimeDB := openRuntimeDB(t, f.dsn)
	repo := repository.RequireTokensRepository(t, runtimeDB, nil)

	_, err := repo.FindActiveByPrefix(context.Background(), f.tokenAPrefix)
	var pqErr *pq.Error
	if !errors.As(err, &pqErr) || string(pqErr.Code) != "42501" {
		t.Fatalf("ibex_runtime FindActiveByPrefix error = %v, want SQLSTATE 42501", err)
	}
}

// openRuntimeDB opens the same database as ibex_runtime, so the reader grant
// can be probed from the login it was revoked from.
func openRuntimeDB(t *testing.T, dsn string) *sql.DB {
	t.Helper()
	parsed, err := url.Parse(dsn)
	if err != nil {
		t.Fatalf("parse test DSN: %v", err)
	}
	parsed.User = url.UserPassword("ibex_runtime", testutil.RuntimeLoginTestPassword)
	db, err := sql.Open("postgres", parsed.String())
	if err != nil {
		t.Fatalf("open runtime pool: %v", err)
	}
	t.Cleanup(func() { _ = db.Close() })
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := db.PingContext(ctx); err != nil {
		t.Fatalf("connect as ibex_runtime: %v", err)
	}
	return db
}
