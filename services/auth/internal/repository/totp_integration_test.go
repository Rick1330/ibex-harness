//go:build integration

package repository_test

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/google/uuid"
)

func newTotpRepo(t *testing.T) (*repository.TotpSecretRepo, string, string) {
	t.Helper()
	dsn, cleanup := testutil.SetupPostgres(t)
	t.Cleanup(cleanup)
	db := testutil.OpenDB(t, dsn)
	t.Cleanup(func() { _ = db.Close() })
	orgID := testutil.SeedOrganization(t, db, "TOTP Org", "totp-"+uuid.NewString()[:8])
	userID := testutil.SeedUser(t, db, orgID, "totp-"+uuid.NewString()[:8]+"@example.com", "TOTP User")
	return repository.NewTotpSecretRepo(db), orgID, userID
}

func mustGet(t *testing.T, repo *repository.TotpSecretRepo, orgID, userID string) repository.TotpSecretRow {
	t.Helper()
	got, err := repo.Get(context.Background(), orgID, userID)
	if err != nil {
		t.Fatalf("get: %v", err)
	}
	return got
}

func TestIntegration_TotpSecretRepo_EmptyGet(t *testing.T) {
	t.Parallel()
	repo, orgID, userID := newTotpRepo(t)
	if _, err := repo.Get(context.Background(), orgID, userID); !errors.Is(err, repository.ErrTotpSecretNotFound) {
		t.Fatalf("empty get: %v", err)
	}
}

func TestIntegration_TotpSecretRepo_UpsertAndReplace(t *testing.T) {
	t.Parallel()
	repo, orgID, userID := newTotpRepo(t)
	ctx := context.Background()
	row := repository.TotpSecretRow{
		OrgID: orgID, UserID: userID,
		Ciphertext: []byte("cipher-one"), WrappedDEK: []byte("dek-one"), EncryptionKeyID: "v1",
	}
	if err := repo.UpsertPending(ctx, row); err != nil {
		t.Fatalf("upsert: %v", err)
	}
	got := mustGet(t, repo, orgID, userID)
	if string(got.Ciphertext) != "cipher-one" {
		t.Fatalf("ciphertext=%q", got.Ciphertext)
	}
	if got.ConfirmedAt.Valid {
		t.Fatal("expected pending")
	}
	row.Ciphertext = []byte("cipher-two")
	row.WrappedDEK = []byte("dek-two")
	if err := repo.UpsertPending(ctx, row); err != nil {
		t.Fatalf("replace: %v", err)
	}
	got = mustGet(t, repo, orgID, userID)
	if string(got.Ciphertext) != "cipher-two" {
		t.Fatalf("ciphertext=%q", got.Ciphertext)
	}
}

func TestIntegration_TotpSecretRepo_ConfirmCAS(t *testing.T) {
	t.Parallel()
	repo, orgID, userID := newTotpRepo(t)
	ctx := context.Background()
	ct := []byte("cipher-two")
	if err := repo.UpsertPending(ctx, repository.TotpSecretRow{
		OrgID: orgID, UserID: userID,
		Ciphertext: ct, WrappedDEK: []byte("dek-two"), EncryptionKeyID: "v1",
	}); err != nil {
		t.Fatalf("upsert: %v", err)
	}
	at := time.Now().UTC().Truncate(time.Second)
	err := repo.ConfirmCiphertext(ctx, repository.ConfirmCiphertextParams{
		OrgID: orgID, UserID: userID, Ciphertext: []byte("wrong"), At: at,
	})
	if !errors.Is(err, repository.ErrTotpSecretNotFound) {
		t.Fatalf("cas miss: %v", err)
	}
	if err := repo.ConfirmCiphertext(ctx, repository.ConfirmCiphertextParams{
		OrgID: orgID, UserID: userID, Ciphertext: ct, At: at,
	}); err != nil {
		t.Fatalf("confirm cas: %v", err)
	}
	got := mustGet(t, repo, orgID, userID)
	if !got.ConfirmedAt.Valid {
		t.Fatal("expected confirmed")
	}
	if err := repo.Confirm(ctx, orgID, userID, at.Add(time.Minute)); !errors.Is(err, repository.ErrTotpSecretNotFound) {
		t.Fatalf("reconfirm: %v", err)
	}
}

func TestIntegration_TotpSecretRepo_ReEnroll(t *testing.T) {
	t.Parallel()
	repo, orgID, userID := newTotpRepo(t)
	ctx := context.Background()
	ct := []byte("cipher-two")
	at := time.Now().UTC().Truncate(time.Second)
	if err := repo.UpsertPending(ctx, repository.TotpSecretRow{
		OrgID: orgID, UserID: userID,
		Ciphertext: ct, WrappedDEK: []byte("dek-two"), EncryptionKeyID: "v1",
	}); err != nil {
		t.Fatalf("upsert: %v", err)
	}
	if err := repo.ConfirmCiphertext(ctx, repository.ConfirmCiphertextParams{
		OrgID: orgID, UserID: userID, Ciphertext: ct, At: at,
	}); err != nil {
		t.Fatalf("confirm: %v", err)
	}
	if err := repo.UpsertPending(ctx, repository.TotpSecretRow{
		OrgID: orgID, UserID: userID,
		Ciphertext: []byte("cipher-three"), WrappedDEK: []byte("dek-3"), EncryptionKeyID: "v1",
	}); err != nil {
		t.Fatalf("re-upsert: %v", err)
	}
	got := mustGet(t, repo, orgID, userID)
	if got.ConfirmedAt.Valid {
		t.Fatal("expected pending again")
	}
	if err := repo.Confirm(ctx, orgID, userID, at); err != nil {
		t.Fatalf("legacy confirm: %v", err)
	}
}

func TestIntegration_TotpSecretRepo_CrossTenantDenied(t *testing.T) {
	t.Parallel()
	dsn, cleanup := testutil.SetupPostgres(t)
	t.Cleanup(cleanup)
	db := testutil.OpenDB(t, dsn)
	t.Cleanup(func() { _ = db.Close() })

	orgA := testutil.SeedOrganization(t, db, "TOTP Org A", "totp-a-"+uuid.NewString()[:8])
	userA := testutil.SeedUser(t, db, orgA, "totp-a-"+uuid.NewString()[:8]+"@example.com", "User A")
	orgB := testutil.SeedOrganization(t, db, "TOTP Org B", "totp-b-"+uuid.NewString()[:8])
	repo := repository.NewTotpSecretRepo(db)
	ctx := context.Background()

	ct := []byte("cipher-org-a")
	if err := repo.UpsertPending(ctx, repository.TotpSecretRow{
		OrgID: orgA, UserID: userA,
		Ciphertext: ct, WrappedDEK: []byte("dek-a"), EncryptionKeyID: "v1",
	}); err != nil {
		t.Fatalf("upsert A: %v", err)
	}

	if _, err := repo.Get(ctx, orgB, userA); !errors.Is(err, repository.ErrTotpSecretNotFound) {
		t.Fatalf("cross-tenant get: %v", err)
	}
	err := repo.ConfirmCiphertext(ctx, repository.ConfirmCiphertextParams{
		OrgID: orgB, UserID: userA, Ciphertext: ct, At: time.Now().UTC(),
	})
	if !errors.Is(err, repository.ErrTotpSecretNotFound) {
		t.Fatalf("cross-tenant confirm: %v", err)
	}
	got := mustGet(t, repo, orgA, userA)
	if got.ConfirmedAt.Valid {
		t.Fatal("org A row must remain pending")
	}
}
