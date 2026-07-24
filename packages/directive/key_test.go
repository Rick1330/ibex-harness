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
	tests := []struct {
		name    string
		channel string
		want    uuid.UUID
		wantErr bool
	}{
		{name: "valid", channel: ChannelForOrg(orgID), want: orgID},
		{name: "wrong_prefix", channel: "other:" + orgID.String(), wantErr: true},
		{name: "malformed_uuid", channel: ChannelPrefix + "not-a-uuid", wantErr: true},
	}
	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			got, err := OrgIDFromChannel(tc.channel)

			if tc.wantErr {
				if err == nil {
					t.Fatal("expected error")
				}
				return
			}
			if err != nil {
				t.Fatalf("OrgIDFromChannel: %v", err)
			}
			if got != tc.want {
				t.Fatalf("got %s want %s", got, tc.want)
			}
		})
	}
}
