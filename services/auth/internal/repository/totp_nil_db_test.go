package repository_test

import (
	"context"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
)

func TestUnit_TotpSecretRepo_NilDB(t *testing.T) {
	t.Parallel()
	repo := repository.NewTotpSecretRepo(nil)
	ctx := context.Background()
	row := repository.TotpSecretRow{OrgID: "o", UserID: "u", Ciphertext: []byte{1}, WrappedDEK: []byte{2}, EncryptionKeyID: "v1"}
	if err := repo.UpsertPending(ctx, row); err == nil {
		t.Fatal("UpsertPending nil db")
	}
	if _, err := repo.Get(ctx, "o", "u"); err == nil {
		t.Fatal("Get nil db")
	}
	if err := repo.Confirm(ctx, "o", "u", time.Now().UTC()); err == nil {
		t.Fatal("Confirm nil db")
	}
	if err := repo.ConfirmCiphertext(ctx, "o", "u", []byte{1}, time.Now().UTC()); err == nil {
		t.Fatal("ConfirmCiphertext nil db")
	}
	var nilRepo *repository.TotpSecretRepo
	if err := nilRepo.UpsertPending(ctx, row); err == nil {
		t.Fatal("nil receiver UpsertPending")
	}
}
