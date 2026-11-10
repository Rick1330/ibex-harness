//go:build integration

package repository_test

import (
	"context"
	"database/sql"
	"errors"
	"testing"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/google/uuid"
	"github.com/lib/pq"
)

// isolationFixture holds two tenants and one row each for the repositories
// under test.
type isolationFixture struct {
	repo   *repository.TokensRepository
	users  *repository.UsersRepository
	agents *repository.AgentsRepository
	totp   *repository.TotpSecretRepo
	creds  *repository.ProviderCredentialsRepository

	orgA, orgB     string
	userA, userB   string
	agentB         string
	tokenA         string
	tokenBPrefix   string
	totpBCipher    []byte
	credName       string
	credCiphertext []byte
}

func newIsolationFixture(t *testing.T) *isolationFixture {
	t.Helper()
	dsn, cleanup := testutil.SetupPostgres(t)
	t.Cleanup(cleanup)
	db := testutil.OpenDB(t, dsn)
	t.Cleanup(func() { _ = db.Close() })

	label := uuid.NewString()[:8]
	orgA := testutil.SeedOrganization(t, db, "Isolation A "+label, "iso-a-"+label)
	orgB := testutil.SeedOrganization(t, db, "Isolation B "+label, "iso-b-"+label)
	userA := testutil.SeedUser(t, db, orgA, "iso-a-"+label+"@test.local", "User A")
	userB := testutil.SeedUser(t, db, orgB, "iso-b-"+label+"@test.local", "User B")
	agentB := testutil.SeedAgent(t, db, orgB, userB, "Agent B", "agent-b-"+label)

	repo := repository.RequireTokensRepository(t, db, nil)
	credRepo, err := repository.NewProviderCredentialsRepository(db, nil)
	if err != nil {
		t.Fatalf("NewProviderCredentialsRepository: %v", err)
	}
	f := &isolationFixture{
		repo: repo, users: repository.NewUsersRepository(db, nil),
		agents: repository.NewAgentsRepository(db, nil),
		totp:   repository.NewTotpSecretRepo(db), creds: credRepo,
		orgA: orgA, orgB: orgB, userA: userA, userB: userB, agentB: agentB,
		credName: "openai", credCiphertext: []byte("org-b-secret"),
	}
	f.seedRows(t, db)
	return f
}

func (f *isolationFixture) seedRows(t *testing.T, db *sql.DB) {
	t.Helper()
	ctx := context.Background()
	idA, err := f.repo.InsertTestToken(ctx, repository.TestTokenParams{
		OrgID: f.orgA, Prefix: "ibex_pat_" + uuid.NewString(), Hash: "hash-a-" + uuid.NewString(), Name: "a", Permissions: 1,
	})
	if err != nil {
		t.Fatalf("seed token A: %v", err)
	}
	f.tokenA = idA
	prefixB := "ibex_pat_" + uuid.NewString()
	if _, err := f.repo.InsertTestToken(ctx, repository.TestTokenParams{
		OrgID: f.orgB, Prefix: prefixB, Hash: "hash-b-" + uuid.NewString(), Name: "b", Permissions: 1,
	}); err != nil {
		t.Fatalf("seed token B: %v", err)
	}
	f.tokenBPrefix = prefixB
	f.totpBCipher = []byte("org-b-totp")
	if err := f.totp.UpsertPending(ctx, repository.TotpSecretRow{
		OrgID: f.orgB, UserID: f.userB, Ciphertext: f.totpBCipher,
		WrappedDEK: []byte("dek-b"), EncryptionKeyID: "v1",
	}); err != nil {
		t.Fatalf("seed TOTP B: %v", err)
	}
	if _, err := f.creds.Upsert(ctx, repository.ProviderCredentialRow{
		OrgID: f.orgB, ProviderName: f.credName, Ciphertext: f.credCiphertext,
		WrappedDEK: []byte("dek-b"), EncryptionKeyID: "v1", KeyHint: "hint", Status: "active",
	}); err != nil {
		t.Fatalf("seed credential B: %v", err)
	}
}

// TestRepositoryCrossTenantNegatives runs every tenant operation at the real
// ibex_app role and proves org A cannot observe or mutate org B's rows. A
// missing row must be a miss (nil record or sentinel), never SQLSTATE 42501: a
// permission error here would mean the pin is wrong and an outage is hidden as
// a cross-tenant denial.
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

func assertCrossTenantSentinel(t *testing.T, label string, want error, call func() error) {
	t.Helper()
	err := call()
	assertNoPermissionError(t, err)
	if !errors.Is(err, want) {
		t.Fatalf("cross-tenant %s = %v, want %v", label, err, want)
	}
}

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

func assertCrossTenantTokenList(t *testing.T, ctx context.Context, f *isolationFixture) {
	t.Helper()
	rows, _, err := f.repo.ListTokens(ctx, f.orgA, "", 100)
	assertNoPermissionError(t, err)
	if err != nil {
		t.Fatalf("list tokens: %v", err)
	}
	for _, row := range rows {
		if row.Prefix == f.tokenBPrefix {
			t.Fatalf("org A listed org B token %s", row.Prefix)
		}
	}
}

func lookupTokenID(t *testing.T, f *isolationFixture, prefix string) string {
	t.Helper()
	row, err := f.repo.FindActiveByPrefix(context.Background(), prefix)
	if err != nil {
		t.Fatalf("lookup token %s: %v", prefix, err)
	}
	return row.ID
}

func assertNoPermissionError(t *testing.T, err error) {
	t.Helper()
	var pqErr *pq.Error
	if errors.As(err, &pqErr) && string(pqErr.Code) == "42501" {
		t.Fatalf("operation failed with a permission error, not a tenant miss: %v", err)
	}
}
