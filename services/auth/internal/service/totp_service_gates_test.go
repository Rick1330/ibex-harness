package service_test

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/services/auth/internal/service"
	"github.com/pquerna/otp/totp"
)

func TestUnit_TotpService_Disabled(t *testing.T) {
	t.Parallel()
	disabled, err := service.NewTotpService(&memTOTPStore{}, service.MasterKeyConfig{}, false, nil)
	if err != nil {
		t.Fatal(err)
	}
	_, err = disabled.BeginEnrollment(context.Background(), beginP(refShort, "a"))
	if !errors.Is(err, service.ErrTOTPDisabled) {
		t.Fatalf("disabled: %v", err)
	}
}

func TestUnit_TotpService_NotReadyAndNilRepo(t *testing.T) {
	t.Parallel()
	notReady, err := service.NewTotpService(&memTOTPStore{}, service.MasterKeyConfig{}, true, nil)
	if err != nil {
		t.Fatal(err)
	}
	_, err = notReady.BeginEnrollment(context.Background(), beginP(refShort, "a"))
	if !errors.Is(err, service.ErrTOTPNotReady) {
		t.Fatalf("not ready: %v", err)
	}
	if _, err := service.NewTotpService(nil, service.MasterKeyConfig{}, true, nil); err == nil {
		t.Fatal("expected nil repo error")
	}
}

func TestUnit_TotpService_MissingJWTAndGates(t *testing.T) {
	t.Parallel()
	store := &memTOTPStore{}
	kek, _ := mustMasterEncoded(t)
	noJWT, err := service.NewTotpService(store, kek, true, nil)
	if err != nil {
		t.Fatal(err)
	}
	_, _, err = noJWT.CreateStepUp(context.Background(), stepUpP(refShort, "123456", 1))
	if !errors.Is(err, service.ErrSessionJWTMissing) {
		t.Fatalf("missing jwt: %v", err)
	}
	ready, err := service.NewTotpService(store, kek, true, mustIssuer(t))
	if err != nil {
		t.Fatal(err)
	}
	emptyOrg := service.TenantRef{Org: "", User: "u"}
	_, err = ready.BeginEnrollment(context.Background(), beginP(emptyOrg, "a"))
	if !errors.Is(err, service.ErrInvalidArgument) {
		t.Fatalf("empty org: %v", err)
	}
	_, _, err = ready.CreateStepUp(context.Background(), stepUpP(refShort, "123456", 1))
	if !errors.Is(err, service.ErrTOTPNotEnrolled) {
		t.Fatalf("not enrolled: %v", err)
	}
}

func TestUnit_TotpAttempts_Lockout(t *testing.T) {
	t.Parallel()
	kek, mk := mustMasterEncoded(t)
	store := &memTOTPStore{master: mk}
	svc, err := service.NewTotpService(store, kek, true, mustIssuer(t))
	if err != nil {
		t.Fatal(err)
	}
	if _, err := svc.BeginEnrollment(context.Background(), beginP(refOrg, "acct")); err != nil {
		t.Fatal(err)
	}
	for i := 0; i < 5; i++ {
		err := svc.ConfirmEnrollment(context.Background(), confirmP(refOrg, "000000"))
		if !errors.Is(err, service.ErrTOTPInvalidCode) {
			t.Fatalf("attempt %d: %v", i, err)
		}
	}
	err = svc.ConfirmEnrollment(context.Background(), confirmP(refOrg, "000000"))
	if !errors.Is(err, service.ErrTOTPLockedOut) {
		t.Fatalf("want lockout, got %v", err)
	}
}

func TestUnit_TotpService_ConfirmPendingAndRepoErrors(t *testing.T) {
	t.Parallel()
	kek, mk := mustMasterEncoded(t)
	kek.KeyID = ""
	store := &memTOTPStore{master: mk}
	svc, err := service.NewTotpService(store, kek, true, mustIssuer(t))
	if err != nil {
		t.Fatal(err)
	}
	if _, err := svc.BeginEnrollment(context.Background(), beginP(refOrg, "acct")); err != nil {
		t.Fatal(err)
	}
	err = svc.ConfirmEnrollment(context.Background(), confirmP(refOrg, "000000"))
	if !errors.Is(err, service.ErrTOTPInvalidCode) {
		t.Fatalf("bad code: %v", err)
	}
	secret := store.plaintext(t, refOrg)
	code, err := totp.GenerateCode(secret, time.Now().UTC())
	if err != nil {
		t.Fatal(err)
	}
	_, _, err = svc.CreateStepUp(context.Background(), stepUpP(refOrg, code, 1))
	if !errors.Is(err, service.ErrTOTPNotEnrolled) {
		t.Fatalf("pending stepup: %v", err)
	}
	if err := svc.ConfirmEnrollment(context.Background(), confirmP(refOrg, code)); err != nil {
		t.Fatal(err)
	}
	err = svc.ConfirmEnrollment(context.Background(), confirmP(refOrg, code))
	if !errors.Is(err, service.ErrTOTPAlreadyDone) {
		t.Fatalf("already done confirm: %v", err)
	}
}

func TestUnit_TotpService_RepoGetErrorSurfaces(t *testing.T) {
	t.Parallel()
	kek, mk := mustMasterEncoded(t)
	store := &errGetStore{memTOTPStore: memTOTPStore{master: mk}, getErr: errors.New("db down")}
	svc, err := service.NewTotpService(store, kek, true, mustIssuer(t))
	if err != nil {
		t.Fatal(err)
	}
	_, err = svc.BeginEnrollment(context.Background(), beginP(refShort, "a"))
	if err == nil || err.Error() != "db down" {
		t.Fatalf("want db down, got %v", err)
	}
}
