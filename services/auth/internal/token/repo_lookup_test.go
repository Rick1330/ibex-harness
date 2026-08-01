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
	lookup, err := token.NewRepoLookup(stubRepoLookup{row: sampleRepoTokenRow(agentID, userID, expires)})
	if err != nil {
		t.Fatalf("NewRepoLookup: %v", err)
	}
	got, err := lookup.FindActiveByPrefix(context.Background(), "pfx")
	if err != nil {
		t.Fatalf("FindActiveByPrefix: %v", err)
	}
	assertMappedRow(t, got, agentID, userID, expires)
}

func TestUnit_NewRepoLookup_RejectsNilInner(t *testing.T) {
	t.Parallel()
	if _, err := token.NewRepoLookup(nil); err == nil {
		t.Fatal("expected error")
	}
}

func sampleRepoTokenRow(agentID, userID string, expires time.Time) repository.TokenRow {
	return repository.TokenRow{
		ID: "tid", OrgID: "oid", Hash: "h", Permissions: 3,
		AgentID:   sql.NullString{String: agentID, Valid: true},
		UserID:    sql.NullString{String: userID, Valid: true},
		ExpiresAt: sql.NullTime{Time: expires, Valid: true},
	}
}

func assertMappedRow(t *testing.T, got token.Row, agentID, userID string, expires time.Time) {
	t.Helper()
	assertRowCore(t, got)
	assertOptionalString(t, "agent", got.AgentID, agentID)
	assertOptionalString(t, "user", got.UserID, userID)
	assertOptionalTime(t, got.ExpiresAt, expires)
}

func assertRowCore(t *testing.T, got token.Row) {
	t.Helper()
	if got.ID != "tid" {
		t.Fatalf("id=%q", got.ID)
	}
	if got.OrgID != "oid" {
		t.Fatalf("org_id=%q", got.OrgID)
	}
	if got.Hash != "h" {
		t.Fatalf("hash=%q", got.Hash)
	}
	if got.Permissions != 3 {
		t.Fatalf("permissions=%d", got.Permissions)
	}
}

func assertOptionalString(t *testing.T, label string, got *string, want string) {
	t.Helper()
	if got == nil {
		t.Fatalf("%s: nil", label)
	}
	if *got != want {
		t.Fatalf("%s=%q want %q", label, *got, want)
	}
}

func assertOptionalTime(t *testing.T, got *time.Time, want time.Time) {
	t.Helper()
	if got == nil {
		t.Fatal("expires: nil")
	}
	if !got.Equal(want) {
		t.Fatalf("expires=%v want %v", got, want)
	}
}
