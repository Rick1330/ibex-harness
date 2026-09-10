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

	row := repository.ProviderCredentialRow{
		OrgID: orgA, ProviderName: "openai",
		Ciphertext: []byte("nonce-ciphertext"), WrappedDEK: []byte("nonce-wrapped"),
		EncryptionKeyID: "v1", KeyHint: "cdef", Status: "active",
		BaseURL: sql.NullString{String: "https://byo.example", Valid: true},
	}
	upserted, err := repo.Upsert(ctx, row)
	if err != nil {
		t.Fatalf("Upsert: %v", err)
	}
	if upserted.ID == "" || upserted.OrgID != orgA || !upserted.BaseURL.Valid {
		t.Fatalf("upserted=%+v", upserted)
	}

	found, err := repo.FindByOrgProvider(ctx, orgA, "openai")
	if err != nil {
		t.Fatalf("Find: %v", err)
	}
	if string(found.Ciphertext) != "nonce-ciphertext" || found.KeyHint != "cdef" {
		t.Fatalf("found=%+v", found)
	}

	listed, err := repo.ListByOrg(ctx, orgA)
	if err != nil || len(listed) != 1 {
		t.Fatalf("list=%+v err=%v", listed, err)
	}

	_, err = repo.FindByOrgProvider(ctx, orgB, "openai")
	if !errors.Is(err, repository.ErrProviderCredentialNotFound) {
		t.Fatalf("cross-tenant find: %v", err)
	}
	listedB, err := repo.ListByOrg(ctx, orgB)
	if err != nil || len(listedB) != 0 {
		t.Fatalf("cross-tenant list=%+v err=%v", listedB, err)
	}

	row.Ciphertext = []byte("rotated-ct")
	row.BaseURL = sql.NullString{}
	updated, err := repo.Upsert(ctx, row)
	if err != nil {
		t.Fatalf("Upsert rotate: %v", err)
	}
	if string(updated.Ciphertext) != "rotated-ct" || updated.BaseURL.Valid {
		t.Fatalf("updated=%+v", updated)
	}

	if err := repo.Delete(ctx, orgA, "openai"); err != nil {
		t.Fatalf("Delete: %v", err)
	}
	if err := repo.Delete(ctx, orgA, "openai"); !errors.Is(err, repository.ErrProviderCredentialNotFound) {
		t.Fatalf("second delete: %v", err)
	}
	_, err = repo.FindByOrgProvider(ctx, orgA, "openai")
	if !errors.Is(err, repository.ErrProviderCredentialNotFound) {
		t.Fatalf("after delete: %v", err)
	}
}
