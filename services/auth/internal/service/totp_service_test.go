package service_test

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/services/auth/internal/service"
	"github.com/pquerna/otp/totp"
)

func TestUnit_TotpService_EnrollmentConfirmAndStepUp(t *testing.T) {
	t.Parallel()
	kek, mk := mustMasterEncoded(t)
	store := &memTOTPStore{master: mk}
	svc, err := service.NewTotpService(store, kek, true, mustIssuer(t))
	if err != nil {
		t.Fatal(err)
	}
	uri, err := svc.BeginEnrollment(context.Background(), beginP(refOrg1, "user-1@example.com"))
	if err != nil {
		t.Fatalf("begin: %v", err)
	}
	if uri == "" {
		t.Fatal("begin: empty uri")
	}
	secret := store.plaintext(t, refOrg1)
	code, err := totp.GenerateCode(secret, time.Now().UTC())
	if err != nil {
		t.Fatal(err)
	}
	if err := svc.ConfirmEnrollment(context.Background(), confirmP(refOrg1, code)); err != nil {
		t.Fatalf("confirm: %v", err)
	}
	_, err = svc.BeginEnrollment(context.Background(), beginP(refOrg1, "again"))
	if !errors.Is(err, service.ErrTOTPAlreadyDone) {
		t.Fatalf("want already done, got %v", err)
	}
	assertStepUpOK(t, svc, secret, refOrg1)
}

func assertStepUpOK(t *testing.T, svc *service.TotpService, secret string, ref service.TenantRef) {
	t.Helper()
	code, err := totp.GenerateCode(secret, time.Now().UTC())
	if err != nil {
		t.Fatal(err)
	}
	tok, exp, err := svc.CreateStepUp(context.Background(), stepUpP(ref, code, 7))
	if err != nil {
		t.Fatalf("stepup: %v", err)
	}
	if tok == "" || exp.IsZero() {
		t.Fatalf("stepup tok=%q exp=%v", tok, exp)
	}
	_, _, err = svc.CreateStepUp(context.Background(), stepUpP(ref, "000000", 7))
	if !errors.Is(err, service.ErrTOTPInvalidCode) {
		t.Fatalf("want invalid code, got %v", err)
	}
}
