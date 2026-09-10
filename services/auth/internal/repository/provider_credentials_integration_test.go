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
	ctx := context.Background()

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
	if upserted.ID == "" || upserted.OrgID != orgID || !upserted.BaseURL.Valid {
		t.Fatalf("upserted=%+v", upserted)
	}
}

func assertFindOpenAI(t *testing.T, repo *repository.ProviderCredentialsRepository, orgID string) {
	t.Helper()
	found, err := repo.FindByOrgProvider(context.Background(), orgID, "openai")
	if err != nil {
		t.Fatalf("Find: %v", err)
	}
	if string(found.Ciphertext) != "nonce-ciphertext" || found.KeyHint != "cdef" {
		t.Fatalf("found=%+v", found)
	}
}

func assertListLen(t *testing.T, repo *repository.ProviderCredentialsRepository, orgID string, n int) {
	t.Helper()
	listed, err := repo.ListByOrg(context.Background(), orgID)
	if err != nil || len(listed) != n {
		t.Fatalf("list=%+v err=%v", listed, err)
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
	if string(updated.Ciphertext) != "rotated-ct" || updated.BaseURL.Valid {
		t.Fatalf("updated=%+v", updated)
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
