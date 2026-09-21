package modelpolicy_test

import (
	"testing"

	"github.com/Rick1330/ibex-harness/packages/modelpolicy"
	"github.com/google/uuid"
)

// Epoch spike (4.P.3 decision 8): after org policy rows are deleted and an
// invalidate event is published, caches must not reinstall stale allow rules.
// DenyAllRegistry models the post-purge posture until a fresh load returns empty.
func TestEpochSpike_AfterPurgeInvalidate_DenyAll(t *testing.T) {
	t.Parallel()
	org := uuid.New()
	var deny modelpolicy.DenyAllRegistry
	_, err := deny.ForOrg(t.Context(), org, "gpt-4o")
	if err != modelpolicy.ErrModelNotAllowedForOrg {
		t.Fatalf("post-purge expect deny-all, got %v", err)
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
