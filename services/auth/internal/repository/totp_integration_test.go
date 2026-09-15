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

func TestIntegration_TotpSecretRepo_UpsertGetConfirm(t *testing.T) {
	t.Parallel()
	dsn, cleanup := testutil.SetupPostgres(t)
	t.Cleanup(cleanup)
	db := testutil.OpenDB(t, dsn)
	t.Cleanup(func() { _ = db.Close() })

	orgID := testutil.SeedOrganization(t, db, "TOTP Org", "totp-"+uuid.NewString()[:8])
	userID := testutil.SeedUser(t, db, orgID, "totp-"+uuid.NewString()[:8]+"@example.com", "TOTP User")
	repo := repository.NewTotpSecretRepo(db)
	ctx := context.Background()

	if _, err := repo.Get(ctx, orgID, userID); !errors.Is(err, repository.ErrTotpSecretNotFound) {
		t.Fatalf("empty get: %v", err)
	}

	ct1 := []byte("cipher-one")
	row := repository.TotpSecretRow{
		OrgID: orgID, UserID: userID,
		Ciphertext: ct1, WrappedDEK: []byte("dek-one"), EncryptionKeyID: "v1",
	}
	if err := repo.UpsertPending(ctx, row); err != nil {
		t.Fatalf("upsert: %v", err)
	}
	got, err := repo.Get(ctx, orgID, userID)
	if err != nil {
		t.Fatalf("get: %v", err)
	}
	if string(got.Ciphertext) != "cipher-one" || got.ConfirmedAt.Valid {
		t.Fatalf("got=%+v", got)
	}

	ct2 := []byte("cipher-two")
	row.Ciphertext = ct2
	row.WrappedDEK = []byte("dek-two")
	if err := repo.UpsertPending(ctx, row); err != nil {
		t.Fatalf("replace: %v", err)
	}
	got, err = repo.Get(ctx, orgID, userID)
	if err != nil {
		t.Fatalf("get2: %v", err)
	}
	if string(got.Ciphertext) != "cipher-two" {
		t.Fatalf("ciphertext=%q", got.Ciphertext)
	}

	at := time.Now().UTC().Truncate(time.Second)
	if err := repo.ConfirmCiphertext(ctx, orgID, userID, []byte("wrong"), at); !errors.Is(err, repository.ErrTotpSecretNotFound) {
		t.Fatalf("cas miss: %v", err)
	}
	if err := repo.ConfirmCiphertext(ctx, orgID, userID, ct2, at); err != nil {
		t.Fatalf("confirm cas: %v", err)
	}
	got, err = repo.Get(ctx, orgID, userID)
	if err != nil || !got.ConfirmedAt.Valid {
		t.Fatalf("confirmed: %+v err=%v", got, err)
	}

	// Already confirmed → Confirm (legacy nil ciphertext) finds nothing pending.
	if err := repo.Confirm(ctx, orgID, userID, at.Add(time.Minute)); !errors.Is(err, repository.ErrTotpSecretNotFound) {
		t.Fatalf("reconfirm: %v", err)
	}

	// Re-enroll clears confirmed_at.
	if err := repo.UpsertPending(ctx, repository.TotpSecretRow{
		OrgID: orgID, UserID: userID,
		Ciphertext: []byte("cipher-three"), WrappedDEK: []byte("dek-3"), EncryptionKeyID: "v1",
	}); err != nil {
		t.Fatalf("re-upsert: %v", err)
	}
	got, err = repo.Get(ctx, orgID, userID)
	if err != nil || got.ConfirmedAt.Valid {
		t.Fatalf("pending again: %+v err=%v", got, err)
	}
	if err := repo.Confirm(ctx, orgID, userID, at); err != nil {
		t.Fatalf("legacy confirm: %v", err)
	}
}
