package token_test

import (
	"context"
	"database/sql"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
)

type stubRepoLookup struct {
	row repository.TokenRow
	err error
}

func (s stubRepoLookup) FindActiveByPrefix(context.Context, string) (repository.TokenRow, error) {
	return s.row, s.err
}

func TestRepoLookup_FindActiveByPrefix(t *testing.T) {
	t.Parallel()
	agentID := "agent-1"
	userID := "user-1"
	expires := time.Date(2026, 7, 1, 0, 0, 0, 0, time.UTC)
	inner := stubRepoLookup{row: repository.TokenRow{
		ID: "tid", OrgID: "oid", Hash: "h", Permissions: 3,
		AgentID:   sql.NullString{String: agentID, Valid: true},
		UserID:    sql.NullString{String: userID, Valid: true},
		ExpiresAt: sql.NullTime{Time: expires, Valid: true},
	}}
	got, err := token.RepoLookup{Inner: inner}.FindActiveByPrefix(context.Background(), "pfx")
	if err != nil {
		t.Fatalf("FindActiveByPrefix: %v", err)
	}
	if got.ID != "tid" || got.OrgID != "oid" || got.Hash != "h" || got.Permissions != 3 {
		t.Fatalf("row: %+v", got)
	}
	if got.AgentID == nil || *got.AgentID != agentID {
		t.Fatalf("agent: %+v", got.AgentID)
	}
	if got.UserID == nil || *got.UserID != userID {
		t.Fatalf("user: %+v", got.UserID)
	}
	if got.ExpiresAt == nil || !got.ExpiresAt.Equal(expires) {
		t.Fatalf("expires: %+v", got.ExpiresAt)
	}
}
