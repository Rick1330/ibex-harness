package authcache

import (
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
)

func TestUnit_OrgIndex_PrunesExpiredTombsOnRevoke(t *testing.T) {
	t.Parallel()
	now := time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC)
	idx := newOrgIndex(time.Minute, func() time.Time { return now })

	expired := uuid.MustParse("11111111-1111-1111-1111-111111111111")
	live := uuid.MustParse("22222222-2222-2222-2222-222222222222")
	_ = idx.revoke(expired.String())
	now = now.Add(2 * time.Minute)
	_ = idx.revoke(live.String())

	idx.mu.RLock()
	defer idx.mu.RUnlock()
	if _, ok := idx.tomb[expired.String()]; ok {
		t.Fatal("expected expired tombstone pruned")
	}
	if _, ok := idx.tomb[live.String()]; !ok {
		t.Fatal("expected live tombstone retained")
	}
}

func TestUnit_OrgIndex_RevokeCanonicalizesMixedCaseUUID(t *testing.T) {
	t.Parallel()
	orgID := uuid.MustParse("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
	idx := newOrgIndex(time.Minute, time.Now)
	hash := digest("h1")
	if !idx.put(orgID, hash) {
		t.Fatal("put should succeed")
	}
	mixed := strings.ToUpper(orgID.String())
	got := idx.revoke(mixed)
	if len(got) != 1 {
		t.Fatalf("revoke digests=%d want 1", len(got))
	}
	if idx.isSuspended(orgID) != true {
		t.Fatal("expected suspended after mixed-case revoke")
	}
	if idx.put(orgID, hash) {
		t.Fatal("put should reject while tombstone live")
	}
}

func TestUnit_OrgIndex_RevokeRejectsMalformed(t *testing.T) {
	t.Parallel()
	idx := newOrgIndex(time.Minute, time.Now)
	if got := idx.revoke("not-a-uuid"); got != nil {
		t.Fatalf("got=%v want nil", got)
	}
}
