package repository_test

import (
	"context"
	"database/sql"
	"errors"
	"testing"

	// Register the postgres driver so sql.Open("postgres", ...) can return a non-nil *sql.DB.
	_ "github.com/lib/pq"

	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
)

func TestUnit_NewProviderCredentialsRepository_NilDB(t *testing.T) {
	t.Parallel()
	repo, err := repository.NewProviderCredentialsRepository(nil, nil)
	if err == nil || repo != nil {
		t.Fatalf("repo=%v err=%v", repo, err)
	}
	if !errors.Is(err, repository.ErrNilDB) {
		t.Fatalf("err=%v", err)
	}
}

func TestUnit_ProviderCredentialsRepository_BeginTxFails(t *testing.T) {
	t.Parallel()
	db, err := sql.Open("postgres", "postgres://127.0.0.1:1/unused?sslmode=disable")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	repo, err := repository.NewProviderCredentialsRepository(db, nil)
	if err != nil {
		t.Fatal(err)
	}
	ctx := context.Background()
	if _, err := repo.FindByOrgProvider(ctx, "00000000-0000-0000-0000-000000000001", "openai"); err == nil {
		t.Fatal("expected begin/tx error")
	}
	if _, err := repo.ListByOrg(ctx, "00000000-0000-0000-0000-000000000001"); err == nil {
		t.Fatal("expected begin/tx error")
	}
	if err := repo.Delete(ctx, "00000000-0000-0000-0000-000000000001", "openai"); err == nil {
		t.Fatal("expected begin/tx error")
	}
	if _, err := repo.Upsert(ctx, repository.ProviderCredentialRow{
		OrgID: "00000000-0000-0000-0000-000000000001", ProviderName: "openai",
		Ciphertext: []byte("ct"), WrappedDEK: []byte("dek"), EncryptionKeyID: "v1",
		KeyHint: "hint", Status: "active",
	}); err == nil {
		t.Fatal("expected begin/tx error")
	}
}
