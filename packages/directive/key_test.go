package directive

import (
	"testing"

	"github.com/google/uuid"
)

func TestUnit_CacheKeyFormat(t *testing.T) {
	t.Parallel()
	orgID := uuid.MustParse("11111111-1111-1111-1111-111111111111")
	agentID := uuid.MustParse("22222222-2222-2222-2222-222222222222")
	got := cacheKey(orgID, agentID)
	want := "11111111-1111-1111-1111-111111111111:directive:22222222-2222-2222-2222-222222222222"
	if got != want {
		t.Fatalf("cacheKey=%q want %q", got, want)
	}
}

func TestUnit_OrgIDFromChannel(t *testing.T) {
	t.Parallel()
	orgID := uuid.New()
	got, err := OrgIDFromChannel(ChannelForOrg(orgID))
	if err != nil {
		t.Fatalf("OrgIDFromChannel: %v", err)
	}
	if got != orgID {
		t.Fatalf("got %s want %s", got, orgID)
	}
	if _, err := OrgIDFromChannel("other:x"); err == nil {
		t.Fatal("expected error")
	}
}
