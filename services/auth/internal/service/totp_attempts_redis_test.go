package service_test

import (
	"errors"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/services/auth/internal/service"
	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
)

func tenant(org, user string) service.TenantRef {
	return service.TenantRef{Org: service.OrgID(org), User: service.UserID(user)}
}

func TestUnit_RedisTOTPAttempts_LockoutAndReset(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	rdb := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = rdb.Close() })
	if _, err := service.NewRedisTOTPAttempts(nil, 5, time.Minute); err == nil {
		t.Fatal("expected nil client error")
	}
	gate, err := service.NewRedisTOTPAttempts(rdb, 3, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	for i := 0; i < 3; i++ {
		if err := gate.Allow(tenant("org", "user")); err != nil {
			t.Fatalf("allow %d: %v", i, err)
		}
		gate.Fail(tenant("org", "user")) // no-op; reservation already counted
	}
	if err := gate.Allow(tenant("org", "user")); !errors.Is(err, service.ErrTOTPLockedOut) {
		t.Fatalf("want lockout, got %v", err)
	}
	gate.Reset(tenant("org", "user"))
	if err := gate.Allow(tenant("org", "user")); err != nil {
		t.Fatalf("after reset: %v", err)
	}
}

func TestUnit_RedisTOTPAttempts_ReleaseUndoesReservation(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	rdb := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = rdb.Close() })
	gate, err := service.NewRedisTOTPAttempts(rdb, 2, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	if err := gate.Allow(tenant("org", "user")); err != nil {
		t.Fatal(err)
	}
	gate.Release(tenant("org", "user")) // undo infra failure reservation
	if err := gate.Allow(tenant("org", "user")); err != nil {
		t.Fatalf("after release: %v", err)
	}
	if err := gate.Allow(tenant("org", "user")); err != nil {
		t.Fatal(err)
	}
	if err := gate.Allow(tenant("org", "user")); !errors.Is(err, service.ErrTOTPLockedOut) {
		t.Fatalf("want lockout after 2 kept reservations, got %v", err)
	}
}

func TestUnit_TotpService_WithAttemptGate(t *testing.T) {
	t.Parallel()
	store := &memTOTPStore{}
	svc, err := service.NewTotpService(store, service.MasterKeyConfig{}, false, nil)
	if err != nil {
		t.Fatal(err)
	}
	mr := miniredis.RunT(t)
	rdb := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = rdb.Close() })
	gate, err := service.NewRedisTOTPAttempts(rdb, 5, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	if svc.WithAttemptGate(gate) != svc {
		t.Fatal("expected same receiver")
	}
	if svc.WithAttemptGate(nil) != svc {
		t.Fatal("nil gate no-op")
	}
}
