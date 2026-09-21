package service_test

import (
	"context"
	"errors"
	"testing"

	"github.com/Rick1330/ibex-harness/services/auth/internal/service"
)

func TestUnit_TotpService_ReleaseOnNotEnrolled(t *testing.T) {
	t.Parallel()
	gate := mustRedisGate(t, 3)
	kek, mk := mustMasterEncoded(t)
	svc, err := service.NewTotpService(&memTOTPStore{master: mk}, kek, true, mustIssuer(t))
	if err != nil {
		t.Fatal(err)
	}
	svc.WithAttemptGate(gate)
	for i := 0; i < 4; i++ {
		_, _, err = svc.CreateStepUp(context.Background(), stepUpP(refOrg, "123456", 1))
		if !errors.Is(err, service.ErrTOTPNotEnrolled) {
			t.Fatalf("iter %d: %v", i, err)
		}
	}
}

func TestUnit_TotpService_ReleaseOnConfirmRepoError(t *testing.T) {
	t.Parallel()
	gate := mustRedisGate(t, 3)
	kek, mk := mustMasterEncoded(t)
	errStore := &errGetStore{memTOTPStore: memTOTPStore{master: mk}, getErr: errors.New("db down")}
	svc, err := service.NewTotpService(errStore, kek, true, mustIssuer(t))
	if err != nil {
		t.Fatal(err)
	}
	svc.WithAttemptGate(gate)
	err = svc.ConfirmEnrollment(context.Background(), confirmP(refOrg2, "000000"))
	if err == nil || err.Error() != "db down" {
		t.Fatalf("confirm repo err: %v", err)
	}
	if err := gate.Allow(refOrg2); err != nil {
		t.Fatalf("reservation should have been released: %v", err)
	}
}
