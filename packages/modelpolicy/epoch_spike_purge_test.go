package modelpolicy_test

import (
	"testing"

	"github.com/Rick1330/ibex-harness/packages/modelpolicy"
	"github.com/google/uuid"
)

// DenyAllRegistry models the fail-closed posture while the policy store is
// unavailable. It is not the normal result of deleting policy rows: an
// available store with no matching policy has separate ADR-0075 semantics.
func TestDenyAllRegistry_PolicyStoreUnavailable(t *testing.T) {
	t.Parallel()
	org := uuid.New()
	var deny modelpolicy.DenyAllRegistry
	_, err := deny.ForOrg(t.Context(), org, "gpt-4o")
	if err != modelpolicy.ErrPolicyUnavailable {
		t.Fatalf("expect unavailable policy store, got %v", err)
	}
	ev, err := modelpolicy.ParseInvalidateEvent(
		`{"v":1,"org_id":"` + org.String() + `","epoch":999}`,
	)
	if err != nil {
		t.Fatal(err)
	}
	if ev.Epoch != 999 || ev.OrgID != org.String() {
		t.Fatalf("event=%+v", ev)
	}
}
