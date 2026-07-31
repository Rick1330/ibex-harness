package grpcserver

import (
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/services/auth/internal/service"
)

func sampleTokenListItem() service.TokenListItem {
	created := time.Date(2026, 1, 2, 3, 4, 5, 0, time.UTC)
	expires := created.Add(24 * time.Hour)
	revoked := created.Add(time.Hour)
	return service.TokenListItem{
		ID: "tid", Name: "n", Prefix: "ibex_pat_x", Permissions: 99, CreatedAt: created,
		ExpiresAt: &expires, RevokedAt: &revoked, IsRevoked: true,
	}
}

func TestUnit_TokenListToProto_identity(t *testing.T) {
	t.Parallel()
	row := sampleTokenListItem()
	out := tokenListToProto([]service.TokenListItem{row})
	if len(out) != 1 {
		t.Fatalf("len=%d", len(out))
	}
	m := out[0]
	if m.GetTokenId() != row.ID || m.GetName() != row.Name {
		t.Fatalf("metadata: %+v", m)
	}
}

func TestUnit_TokenListToProto_revoked(t *testing.T) {
	t.Parallel()
	out := tokenListToProto([]service.TokenListItem{sampleTokenListItem()})
	if !out[0].GetIsRevoked() {
		t.Fatal("expected is_revoked true")
	}
}

func TestUnit_TokenListToProto_timestamps(t *testing.T) {
	t.Parallel()
	row := sampleTokenListItem()
	m := tokenListToProto([]service.TokenListItem{row})[0]
	if m.GetCreatedAt().AsTime() != row.CreatedAt {
		t.Fatalf("created_at: %v", m.GetCreatedAt().AsTime())
	}
	if m.GetExpiresAt().AsTime() != *row.ExpiresAt {
		t.Fatalf("expires_at: %v", m.GetExpiresAt().AsTime())
	}
	if m.GetRevokedAt().AsTime() != *row.RevokedAt {
		t.Fatalf("revoked_at: %v", m.GetRevokedAt().AsTime())
	}
}
