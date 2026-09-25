package modelpolicy_test

import (
	"testing"

	"github.com/Rick1330/ibex-harness/packages/modelpolicy"
	"github.com/google/uuid"
)

func TestInvalidateEvent_RequiresEpoch(t *testing.T) {
	t.Parallel()
	org := uuid.New().String()
	_, err := modelpolicy.ParseInvalidateEvent(`{"v":1,"org_id":"` + org + `"}`)
	if err == nil {
		t.Fatal("expected error without epoch")
	}
	ev, err := modelpolicy.ParseInvalidateEvent(`{"v":1,"org_id":"` + org + `","epoch":3}`)
	if err != nil {
		t.Fatal(err)
	}
	if ev.Epoch != 3 {
		t.Fatalf("epoch=%d", ev.Epoch)
	}
}

func TestDenyAllRegistry_ForOrg(t *testing.T) {
	t.Parallel()
	var r modelpolicy.DenyAllRegistry
	_, err := r.ForOrg(t.Context(), uuid.New(), "gpt-4o")
	if err != modelpolicy.ErrPolicyUnavailable {
		t.Fatalf("err=%v", err)
	}
}
