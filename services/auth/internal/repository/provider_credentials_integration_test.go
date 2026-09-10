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
)

func setupProviderCredRepo(t *testing.T) (*repository.ProviderCredentialsRepository, *sql.DB) {
	t.Helper()
	dsn, cleanupPG := testutil.SetupPostgres(t)
	t.Cleanup(cleanupPG)
	db := testutil.OpenDB(t, dsn)
	t.Cleanup(func() { _ = db.Close() })
	repo, err := repository.NewProviderCredentialsRepository(db, nil)
	if err != nil {
		t.Fatalf("NewProviderCredentialsRepository: %v", err)
	}
	return repo, db
}

func TestIntegration_ProviderCredentialsRepository_CRUD(t *testing.T) {
	repo, db := setupProviderCredRepo(t)
	orgA := testutil.SeedOrganization(t, db, "Cred Org A", "cred-a-"+uuid.NewString()[:8])
	orgB := testutil.SeedOrganization(t, db, "Cred Org B", "cred-b-"+uuid.NewString()[:8])

	mustUpsertActive(t, repo, orgA)
	assertFindOpenAI(t, repo, orgA)
	assertListLen(t, repo, orgA, 1)
	assertAbsent(t, repo, orgB)
	mustRotateClearBaseURL(t, repo, orgA)
	mustDeleteTwice(t, repo, orgA)
}

func mustUpsertActive(t *testing.T, repo *repository.ProviderCredentialsRepository, orgID string) {
	t.Helper()
	row := repository.ProviderCredentialRow{
		OrgID: orgID, ProviderName: "openai",
		Ciphertext: []byte("nonce-ciphertext"), WrappedDEK: []byte("nonce-wrapped"),
		EncryptionKeyID: "v1", KeyHint: "cdef", Status: "active",
		BaseURL: sql.NullString{String: "https://byo.example", Valid: true},
	}
	upserted, err := repo.Upsert(context.Background(), row)
	if err != nil {
		t.Fatalf("Upsert: %v", err)
	}
	if upserted.ID == "" {
		t.Fatal("missing id")
	}
	if upserted.OrgID != orgID {
		t.Fatalf("org=%s want %s", upserted.OrgID, orgID)
	}
	if !upserted.BaseURL.Valid {
		t.Fatal("expected base_url")
	}
}

func assertFindOpenAI(t *testing.T, repo *repository.ProviderCredentialsRepository, orgID string) {
	t.Helper()
	found, err := repo.FindByOrgProvider(context.Background(), orgID, "openai")
	if err != nil {
		t.Fatalf("Find: %v", err)
	}
	if string(found.Ciphertext) != "nonce-ciphertext" {
		t.Fatalf("ciphertext=%q", found.Ciphertext)
	}
	if found.KeyHint != "cdef" {
		t.Fatalf("hint=%q", found.KeyHint)
	}
}

func assertListLen(t *testing.T, repo *repository.ProviderCredentialsRepository, orgID string, n int) {
	t.Helper()
	listed, err := repo.ListByOrg(context.Background(), orgID)
	if err != nil {
		t.Fatalf("list err=%v", err)
	}
	if len(listed) != n {
		t.Fatalf("list len=%d want %d", len(listed), n)
	}
}

func assertAbsent(t *testing.T, repo *repository.ProviderCredentialsRepository, orgID string) {
	t.Helper()
	_, err := repo.FindByOrgProvider(context.Background(), orgID, "openai")
	if !errors.Is(err, repository.ErrProviderCredentialNotFound) {
		t.Fatalf("cross-tenant find: %v", err)
	}
	assertListLen(t, repo, orgID, 0)
}

func mustRotateClearBaseURL(t *testing.T, repo *repository.ProviderCredentialsRepository, orgID string) {
	t.Helper()
	updated, err := repo.Upsert(context.Background(), repository.ProviderCredentialRow{
		OrgID: orgID, ProviderName: "openai",
		Ciphertext: []byte("rotated-ct"), WrappedDEK: []byte("nonce-wrapped"),
		EncryptionKeyID: "v1", KeyHint: "cdef", Status: "active",
	})
	if err != nil {
		t.Fatalf("Upsert rotate: %v", err)
	}
	if string(updated.Ciphertext) != "rotated-ct" {
		t.Fatalf("ciphertext=%q", updated.Ciphertext)
	}
	if updated.BaseURL.Valid {
		t.Fatal("expected cleared base_url")
	}
}

func mustDeleteTwice(t *testing.T, repo *repository.ProviderCredentialsRepository, orgID string) {
	t.Helper()
	ctx := context.Background()
	if err := repo.Delete(ctx, orgID, "openai"); err != nil {
		t.Fatalf("Delete: %v", err)
	}
	if err := repo.Delete(ctx, orgID, "openai"); !errors.Is(err, repository.ErrProviderCredentialNotFound) {
		t.Fatalf("second delete: %v", err)
	}
	_, err := repo.FindByOrgProvider(ctx, orgID, "openai")
	if !errors.Is(err, repository.ErrProviderCredentialNotFound) {
		t.Fatalf("after delete: %v", err)
	}
}

// TestIntegration_ProviderCredentials_RLSBackstop proves Postgres RLS alone blocks
// cross-org reads when the service-account GUC is unset (ibex_app + app.current_org_id).
func TestIntegration_ProviderCredentials_RLSBackstop(t *testing.T) {
	repo, db := setupProviderCredRepo(t)
	orgA := testutil.SeedOrganization(t, db, "RLS Org A", "rls-a-"+uuid.NewString()[:8])
	orgB := testutil.SeedOrganization(t, db, "RLS Org B", "rls-b-"+uuid.NewString()[:8])
	mustUpsertActive(t, repo, orgA)

	assertCredCountAsApp(t, db, "", 0)   // no org GUC → invisible
	assertCredCountAsApp(t, db, orgB, 0) // other org → invisible
	assertCredCountAsApp(t, db, orgA, 1) // owning org → visible
}

func assertCredCountAsApp(t *testing.T, db *sql.DB, orgID string, want int) {
	t.Helper()
	ctx := context.Background()
	var count int
	err := testutil.WithAppRole(ctx, db, func(tx *sql.Tx) error {
		if orgID != "" {
			testutil.MustSetOrgContext(t, tx, orgID)
		}
		return tx.QueryRowContext(ctx, `SELECT COUNT(*) FROM ibex_core.provider_credentials`).Scan(&count)
	})
	if err != nil {
		t.Fatalf("count org=%q: %v", orgID, err)
	}
	if count != want {
		t.Fatalf("count org=%q: got %d want %d (RLS backstop)", orgID, count, want)
	}
}
