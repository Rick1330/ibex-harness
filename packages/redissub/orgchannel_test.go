package redissub_test

import (
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/redissub"
	"github.com/google/uuid"
)

func TestUnit_ChannelForOrg(t *testing.T) {
	t.Parallel()
	org := uuid.MustParse("11111111-1111-1111-1111-111111111111")
	got := redissub.ChannelForOrg("ibex:mp:invalidate:", org)
	want := "ibex:mp:invalidate:11111111-1111-1111-1111-111111111111"
	if got != want {
		t.Fatalf("got %q want %q", got, want)
	}
}

func TestUnit_ChannelPattern(t *testing.T) {
	t.Parallel()
	got := redissub.ChannelPattern("ibex:mp:invalidate:")
	if got != "ibex:mp:invalidate:*" {
		t.Fatalf("got %q", got)
	}
}

func TestUnit_OrgIDFromChannel(t *testing.T) {
	t.Parallel()
	org := uuid.New()
	prefix := "ibex:cache:invalidate:"

	tests := []struct {
		name    string
		channel string
		want    uuid.UUID
		wantErr string
	}{
		{
			name:    "good",
			channel: prefix + org.String(),
			want:    org,
		},
		{
			name:    "wrong prefix",
			channel: "other:" + org.String(),
			wantErr: "redissub: unexpected channel",
		},
		{
			name:    "too short",
			channel: prefix,
			wantErr: "redissub: unexpected channel",
		},
		{
			name:    "bad uuid suffix",
			channel: prefix + "not-a-uuid",
			wantErr: "invalid UUID",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			got, err := redissub.OrgIDFromChannel(prefix, tt.channel)
			if tt.wantErr != "" {
				if err == nil {
					t.Fatal("expected error")
				}
				if !strings.Contains(err.Error(), tt.wantErr) {
					t.Fatalf("err=%q want substring %q", err.Error(), tt.wantErr)
				}
				return
			}
			if err != nil {
				t.Fatalf("OrgIDFromChannel: %v", err)
			}
			if got != tt.want {
				t.Fatalf("got %s want %s", got, tt.want)
			}
		})
	}
}
